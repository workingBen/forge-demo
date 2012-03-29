import codecs
import glob
import os
from os import path
import shutil
import uuid
import fnmatch

import utils
from build import ConfigurationError
from lib import task, walk_with_depth, read_file_as_str, cd

@task
def rename_files(build, **kw):
	if 'from' not in kw or 'to' not in kw:
		raise ConfigurationError('rename_files requires "from" and "to" keyword arguments')

	return _rename_or_copy_files(build, kw['from'], kw['to'], rename=True)

@task
def copy_files(build, **kw):
	if 'from' not in kw or 'to' not in kw:
		raise ConfigurationError('copy_files requires "from" and "to" keyword arguments')
		
	return _rename_or_copy_files(build, kw['from'], kw['to'], rename=False, ignore_patterns=kw.get('ignore_patterns'))

class Pattern(object):
	def __init__(self, type, value):
		self.type = type
		self.value = value

def git_ignore(root, patterns):
	classified_patterns = []
	with cd(root):
		for pattern in patterns:
			if pattern:
				if '/' in pattern[:-1]:
					ignored_paths = (Pattern('path', match) for match in glob.glob(pattern))
					classified_patterns.extend(ignored_paths)
				else:
					classified_patterns.append(Pattern('file', pattern))

	def git_ignorer(src, names):
		relative_src = src[len(root):].lstrip(r"""\/""")
		ignored = []
		for name in names:
			for pattern in classified_patterns:
				if pattern.type == 'path':
					if path.join(relative_src, name) == os.path.normpath(pattern.value):
						ignored.append(name)
				elif pattern.type == 'file':
					ignore_name = pattern.value
					if pattern.value[-1] in ('/', '\\'):
						if path.isdir(path.join(src, name)):
							ignore_name = ignore_name[:-1]

					if fnmatch.fnmatch(name, ignore_name):
						ignored.append(name)

		return set(ignored)

	return git_ignorer

@task
def _rename_or_copy_files(build, frm, to, rename=True, ignore_patterns=None):
	if ignore_patterns is None:
		ignore_patterns = []

	from_, to = utils.render_string(build.config, frm), utils.render_string(build.config, to)
	if path.isdir(from_):
		ignore_func = git_ignore(from_, ignore_patterns)
	else:
		ignore_func = None

	if rename:
		build.log.debug('renaming {from_} to {to}'.format(**locals()))
		shutil.move(from_, to)
	else:
		if '*' in to:
			# looks like a glob - last directory in path might not exist.
			tos = glob.glob(path.dirname(to))
			tos = [path.join(t,path.basename(to)) for t in tos]
		else:
			# don't glob in case the to path doesn't exist yet
			tos = [to]
		
		for found_to in tos:
			build.log.debug('copying {from_} to {found_to}'.format(**locals()))
			if path.isdir(from_):
				shutil.copytree(from_, found_to, ignore=ignore_func)
			else:
				shutil.copy(from_, found_to)

@task
def find_and_replace(build, *files, **kwargs):
	'''replace one string with another in a set of files
	
	:param kwargs: must contain ``find`` and ``replace`` keys, 
	representing the string to look for, and string to replace
	with, respectively.
	
	:param kwargs: can also contain the ``template`` boolean
	argument, which determines if we will run the ``replace``
	argument through genshi templating first (defaults to True).
	
	:param files: array of glob patterns to select files
	:param kwargs: must contain ``find`` and ``replace`` keys
	'''
	if "find" not in kwargs:
		raise ConfigurationError("Find not passed in to find_and_replace")
	if "replace" not in kwargs:
		raise ConfigurationError("Replace not passed in to find_and_replace")
	template = kwargs.get('template', True)
	find = kwargs["find"]
	replace = kwargs['replace']
	if template:
		replace = utils.render_string(build.config, replace)

	replace_summary = replace[:60]+'...' if len(replace) > 60 else replace
	build.log.debug("replacing %s with %s" % (find, repr(replace_summary)))

	for glob_str in files:
		found_files = glob.glob(utils.render_string(build.config, glob_str))
		if len(found_files) == 0:
			build.log.warning('No files were found to match pattern "%s"' % glob_str)
		for _file in found_files:
			_replace_in_file(build, _file, find, replace)

@task
def find_and_replace_in_dir(build, root_dir, find, replace, file_suffixes=("html",), template=False, **kw):
	'For all files ending with one of the suffixes, under the root_dir, replace ``find`` with ``replace``'
	if template:
		replace = utils.render_string(build.config, replace)

	build.log.debug("replacing {find} with {replace} in {files}".format(
		find=find, replace=replace, files="{0}/**/*.{1}".format(root_dir, file_suffixes)
	))
	
	found_roots = glob.glob(root_dir)
	if len(found_roots) == 0:
		build.log.warning('No files were found to match pattern "%s"' % root_dir)
	for found_root in found_roots:
		for root, _, files, depth in walk_with_depth(found_root):
			for file_ in files:
				if file_.rpartition('.')[2] in file_suffixes:
					find_with_fixed_path = find.replace("%{back_to_parent}%", "../" * (depth+1))
					replace_with_fixed_path = replace.replace("%{back_to_parent}%", "../" * (depth+1))
					_replace_in_file(build, path.join(root, file_), find_with_fixed_path, replace_with_fixed_path)

def _replace_in_file(build, filename, find, replace):
	build.log.debug("replacing {find} with {replace} in {filename}".format(**locals()))
	
	tmp_file = uuid.uuid4().hex
	in_file_contents = read_file_as_str(filename)
	in_file_contents = in_file_contents.replace(find, replace)
	with codecs.open(tmp_file, 'w', encoding='utf8') as out_file:
		out_file.write(in_file_contents)
	os.remove(filename)
	os.rename(tmp_file, filename)

@task
def set_in_biplist(build, filename, key, value):
	# biplist import must be done here, as in the server context, biplist doesn't exist
	import biplist
	
	value = utils.render_string(build.config, value)
	
	build.log.debug("settings {key} to {value} in {files}".format(
		key=key, value=value, files=filename
	))
	
	found_files = glob.glob(filename)
	if len(found_files) == 0:
		build.log.warning('No files were found to match pattern "%s"' % root_dir)
	for found_file in found_files:
		plist = biplist.readPlist(found_file)
		plist[key] = value
		biplist.writePlist(plist, found_file)

@task
def resolve_urls(build, *url_locations):
	'''Include "src" prefix for relative URLs, e.g. ``file.html`` -> ``src/file.html``
	
	``url_locations`` uses::
	
	* dot-notation to descend into a dictionary
	* ``[]`` at the end of a field name to denote an array
	* ``*`` means all attributes on a dictionary
	'''
	def resolve_url_with_uuid(url):
		return utils._resolve_url(build.config, url, 'src')
	for location in url_locations:
		build.config = utils.transform(build.config, location, resolve_url_with_uuid)

@task
def wrap_activations(build, location):
	'''Wrap user activation code to prevent running in frames if required
	
	'''
	for activation in build.config['activations']:
		if not 'all_frames' in activation or activation['all_frames'] is False:
			for script in activation['scripts']:
				tmp_file = uuid.uuid4().hex
				filename = location+script[3:]
				build.log.debug("wrapping activation {filename}".format(**locals()))
				in_file_contents = read_file_as_str(filename)
				in_file_contents = 'if (forge._disableFrames === undefined || window.location == window.parent.location) {\n'+in_file_contents+'\n}';
				with codecs.open(tmp_file, 'w', encoding='utf8') as out_file:
					out_file.write(in_file_contents)
				os.remove(filename)
				os.rename(tmp_file, filename)
		
@task
def populate_icons(build, platform, icon_list):
	'''
	adds a platform's icons to a build config.
	platform is a string platform, eg. "android"
	icon_list is a list of string dimensions, eg. [36, 48, 72]
	'''
	if 'icons' in build.config:
		if not platform in build.config['icons']:
			build.config['icons'][platform] = {}
		for icon in icon_list:
			str_icon = str(icon)
			if not str_icon in build.config['icons'][platform]:
				try:
					build.config['icons'][platform][str_icon] = \
						build.config['icons'][str_icon]
				except KeyError:
					build.log.warning('missing icon "%s" for platform "%s"' % (str_icon, platform))
	else:
		pass #no icons is valid, though it should have been caught priorly.

@task
def populate_xml_safe_name(build):
	build.config['xml_safe_name'] = build.config["name"].replace('"', '\\"').replace("'", "\\'")

@task
def populate_json_safe_name(build):
	build.config['json_safe_name'] = build.config["name"].replace('"', '\\"')
