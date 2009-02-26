"""
Skipping shell invocations is good, when possible. This wrapper around subprocess does dirty work of
parsing command lines into argv and making sure that no shell magic is being used.
"""

import subprocess, shlex, re, logging, sys, traceback, os
import command, util
if sys.platform=='win32':
    import win32process

_log = logging.getLogger('pymake.process')

_blacklist = re.compile(r'[=\\$><;*?[{~`|&]')
def clinetoargv(cline):
    """
    If this command line can safely skip the shell, return an argv array.
    @returns argv, badchar
    """

    m = _blacklist.search(cline)
    if m is not None:
        return None, m.group(0)

    return shlex.split(cline, comments=True), None

shellwords = (':', '.', 'break', 'cd', 'continue', 'exec', 'exit', 'export',
              'getopts', 'hash', 'pwd', 'readonly', 'return', 'shift', 
              'test', 'times', 'trap', 'umask', 'unset', 'alias',
              'set', 'bind', 'builtin', 'caller', 'command', 'declare',
              'echo', 'enable', 'help', 'let', 'local', 'logout', 
              'printf', 'read', 'shopt', 'source', 'type', 'typeset',
              'ulimit', 'unalias', 'set')

def call(cline, env, cwd, loc, cb, context, echo):
    #TODO: call this once up-front somewhere and save the result?
    shell, msys = util.checkmsyscompat()

    shellreason = None
    if msys and cline.startswith('/'):
        shellreason = "command starts with /"
    else:
        argv, badchar = clinetoargv(cline)
        if argv is None:
            shellreason = "command contains shell-special character '%s'" % (badchar,)
        elif len(argv) and argv[0] in shellwords:
            shellreason = "command starts with shell primitive '%s'" % (argv[0],)

    if shellreason is not None:
        _log.debug("%s: using shell: %s: '%s'", loc, shellreason, cline)
        if msys:
            cline = [shell, "-c", cline]
        context.call(cline, shell=not msys, env=env, cwd=cwd, cb=cb, echo=echo)
        return

    if not len(argv):
        cb(res=0)
        return

    if argv[0] == command.makepypath:
        command.main(argv[1:], env, cwd, context, cb)
        return

    if argv[0:2] == [sys.executable.replace('\\', '/'),
                     command.makepypath.replace('\\', '/')]:
        command.main(argv[2:], env, cwd, context, cb)
        return

    if argv[0].find('/') != -1:
        executable = os.path.join(cwd, argv[0])
    else:
        executable = None

    context.call(argv, executable=executable, shell=False, env=env, cwd=cwd, cb=cb, echo=echo)

def statustoresult(status):
    """
    Convert the status returned from waitpid into a prettier numeric result.
    """
    sig = status & 0xFF
    if sig:
        return -sig

    return status >>8

def getcontext(jcount):
    assert jcount > 0
    return ParallelContext(jcount)

class ParallelContext(object):
    """
    Manages the parallel execution of processes.
    """

    _allcontexts = set()

    def __init__(self, jcount):
        self.jcount = jcount
        self.exit = False

        self.pending = [] # list of (cb, args, kwargs)
        self.running = [] # list of (subprocess, cb)

        self._allcontexts.add(self)

    def finish(self):
        assert len(self.pending) == 0 and len(self.running) == 0, "pending: %i running: %i" % (len(self.pending), len(self.running))
        self._allcontexts.remove(self)

    def run(self):
        while len(self.pending) and len(self.running) < self.jcount:
            cb, args, kwargs = self.pending.pop(0)
            cb(*args, **kwargs)

    def defer(self, cb, *args, **kwargs):
        self.pending.append((cb, args, kwargs))

    def _docall(self, argv, executable, shell, env, cwd, cb, echo):
            if echo is not None:
                print echo
            try:
                p = subprocess.Popen(argv, executable=executable, shell=shell, env=env, cwd=cwd)
            except OSError, e:
                print >>sys.stderr, e
                cb(-127)
                return

            self.running.append((p, cb))

    def call(self, argv, shell, env, cwd, cb, echo, executable=None):
        """
        Asynchronously call the process
        """

        self.defer(self._docall, argv, executable, shell, env, cwd, cb, echo)

    if sys.platform == 'win32':
        @staticmethod
        def _waitany():
            return win32process.WaitForAnyProcess([p for c in ParallelContext._allcontexts for p, cb in c.running])

        @staticmethod
        def _comparepid(pid, process):
            return pid == process

    else:
        @staticmethod
        def _waitany():
            return os.waitpid(-1, 0)

        @staticmethod
        def _comparepid(pid, process):
            return pid == process.pid

    @staticmethod
    def spin():
        """
        Spin the 'event loop', and never return.
        """

        while True:
            clist = list(ParallelContext._allcontexts)
            for c in clist:
                c.run()

            dowait = util.any((len(c.running) for c in ParallelContext._allcontexts))

            if dowait:
                pid, status = ParallelContext._waitany()
                result = statustoresult(status)

                found = False
                for c in ParallelContext._allcontexts:
                    for i in xrange(0, len(c.running)):
                        p, cb = c.running[i]
                        if ParallelContext._comparepid(pid, p):
                            del c.running[i]
                            cb(result)
                            found = True
                            break

                    if found: break

def makedeferrable(usercb, **userkwargs):
    def cb(*args, **kwargs):
        kwargs.update(userkwargs)
        return usercb(*args, **kwargs)

    return cb