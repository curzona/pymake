from setuptools import setup

setup(name='pymake',
      version='1.0.0',
      description=('make.py (and the pymake modules that support it) are an'
                   ' implementation of the make tool which are mostly'
                   'compatible with makefiles written for GNU make.'),
      author='Benjamin Smedberg',
      author_email='benjamin@smedbergs.us',
      url='http://benjamin.smedbergs.us/pymake/',
      license='MIT License',
      packages=['pymake'],
      py_modules=['make', 'mkformat', 'mkparse'],
      scripts=['make.py', 'mkformat.py', 'mkparse.py'],
      entry_points={
          'console_scripts': [
            'make = make:main'
          ]
      }
      )
