from contextlib import contextmanager
from functools import wraps
import os
from os import error, listdir
from os.path import join, isdir, islink

import chardet

# set up BASE_EXCEPTION early - it's relied upon by other imports
# use ForgeError if we're on the client, so it can catch us
try:
	from forge import ForgeError
	BASE_EXCEPTION = ForgeError
except ImportError:
	BASE_EXCEPTION = Exception

from build import Build

class CouldNotLocate(Exception):
	pass

def task(function):
	Build.tasks[function.func_name] = function
	
	@wraps(function)
	def wrapper(*args, **kw):
		return function(*args, **kw)
	return wrapper
	
def predicate(function):
	Build.predicates[function.func_name] = function
	
	@wraps(function)
	def wrapper(*args, **kw):
		return function(*args, **kw)
	return wrapper
	
# modified os.walk() function from Python 2.4 standard library
def walk_with_depth(top, topdown=True, onerror=None, deeplevel=0): # fix 0
	"""Modified directory tree generator.

	For each directory in the directory tree rooted at top (including top
	itself, but excluding '.' and '..'), yields a 4-tuple

		dirpath, dirnames, filenames, deeplevel

	dirpath is a string, the path to the directory.  dirnames is a list of
	the names of the subdirectories in dirpath (excluding '.' and '..').
	filenames is a list of the names of the non-directory files in dirpath.
	Note that the names in the lists are just names, with no path components.
	To get a full path (which begins with top) to a file or directory in
	dirpath, do os.path.join(dirpath, name). 

	----------------------------------------------------------------------
	+ deeplevel is 0-based deep level from top directory
	----------------------------------------------------------------------
	...

	"""

	try:
		names = listdir(top)
	except error, err:
		if onerror is not None:
			onerror(err)
		return

	dirs, nondirs = [], []
	for name in names:
		if isdir(join(top, name)):
			dirs.append(name)
		else:
			nondirs.append(name)

	if topdown:
		yield top, dirs, nondirs, deeplevel # fix 1
	for name in dirs:
		path = join(top, name)
		if not islink(path):
			for x in walk_with_depth(path, topdown, onerror, deeplevel+1): # fix 2
				yield x
	if not topdown:
		yield top, dirs, nondirs, deeplevel # fix 3


@contextmanager
def cd(target_dir):
	'Change directory to :param:`target_dir` as a context manager - i.e. rip off Fabric'
	old_dir = os.getcwd()
	try:
		os.chdir(target_dir)
		yield target_dir
	finally:
		os.chdir(old_dir)

def read_file_as_str(filename):
	with open(filename, 'rb') as in_file:
		file_contents = in_file.read()

	char_result = chardet.detect(file_contents)
	return file_contents.decode(char_result['encoding'])
