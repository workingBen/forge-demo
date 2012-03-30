# XXX should consolidate this with lib
import logging
from os import path
import subprocess
import StringIO
import lib

from genshi.template import NewTextTemplate

LOG = logging.getLogger(__name__)

class ShellError(lib.BASE_EXCEPTION):
	def __init__(self, message, output):
		self.message = message
		self.output = output

	def __str__(self):
		return "%s: %s" % (self.message, self.output)

# # # # # # # # # # # # # # # # # # # 
#
# Data transform
# TODO XPath or similar?
#
# # # # # # # # # # # # # # # # # # # 
def transform(data, node_steps, fn):
	'''Mutate an arbitrary nested dictionary/array combination with the given function.
	
	``node_steps`` is dot-separated instructions on how to arrive at the data node
	which needs changing::
	
		array_name.[]
		dictionary.key_name
		dictionary.*			   // all keys in a dictionary

	:param data: a nested dictionary / array combination
	:type data: ``dict``
	:param node_steps: dot-separated data path, e.g. my_dict.[].*.target_key
	:param fn: mutating function - will be passed the data found at the end
		``node_steps``, and should return the desired new value
	'''
	obj = data.copy()
	list(_handle_all(obj, node_steps.split('.'), fn))
	return obj

def _yield_plain(obj, name):
	'If obj is a dictionary, yield an attribute'
	if hasattr(obj, '__contains__') and name in obj:
		yield obj[name]
def _yield_array(obj):
	'Yield all elements of an array'
	assert hasattr(obj, '__iter__'), 'Expecting an array, got %s' % obj
	for thing in obj:
		yield thing
def _yield_asterisk(obj):
	'Yield all values in a dictionary'
	if hasattr(obj, 'iteritems'):
		for _, value in obj.iteritems():
			yield value
def _yield_any(obj, name):
	'Yield a value, or array or dictionary values'
	if name == '*':
		return _yield_asterisk(obj)
	elif name == '[]':
		return _yield_array(obj)
	else:
		return _yield_plain(obj, name)

def recurse_dict(dictionary, fn):
	'''
	if the property isn't a string, recurse till it is
	'''
	for key, value in dictionary.iteritems():
		if hasattr(value, 'iteritems'):
			recurse_dict(value, fn)
		else:
			dictionary[key] = fn(value)

def _handle_all(obj, steps, fn):
	if len(steps) > 1:
		for value in _yield_any(obj, steps[0]):
			for x in _handle_all(value, steps[1:], fn):
				yield x
	else:
		step = steps[0]
		if step == '*':
			assert hasattr(obj, 'iteritems'), 'Expecting a dictionary, got %s' % obj
			recurse_dict(obj, fn)
		elif step == '[]':
			assert hasattr(obj, '__iter__'), 'Expecting an array, got %s' % obj
			for i, x in enumerate(obj):
				obj[i] = fn(x)
		else:
			if hasattr(obj, '__contains__') and step in obj:
				obj[step] = fn(obj[step])
	
# # # # # # # # # # # # # # # # # # # 
#
# End data transform
#
# # # # # # # # # # # # # # # # # # # 

def render_string(config, in_s):
	'''Render a Genshi template as a string
	
	:param config: data dictionary
	:param in_s: genshi template
	'''
	tmpl = NewTextTemplate(in_s)

	# older versions of python don't allow unicode keyword arguments
	# so we have to encode the keys (for best compatibility in the client side tools)
	config = _encode_unicode_keys(config)
	return tmpl.generate(**config).render('text')

def _encode_unicode_keys(dictionary):
	'''Returns a new dictionary constructed from the given one, but with the keys encoded as strings.
	:param dictionary: dictionary to encode the keys for

	(For use with old versions of python that can't use unicode keys for keyword arguments)'''

	new_items = [(str(k), v) for k, v in dictionary.items()]
	return dict(new_items)

def _resolve_url(config, url, prefix):
	'''Prefix non-absolute URLs with the path to the user's code'''
	if url.startswith('http://') or url.startswith('https://') or url.startswith(prefix):
		return url
	else:
		return prefix + url if url.startswith('/') else prefix + '/' + url

def run_shell(*args, **kw):
	fail_silently = kw.get('fail_silently', False)
	command_log_level = kw.get("command_log_level", logging.DEBUG)

	LOG.debug('Running: {cmd}'.format(cmd=" ".join(args)))
	proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=kw.get('env'))
	output = StringIO.StringIO()

	for line in iter(proc.stdout.readline, ''):
		output.write(line)
		LOG.log(command_log_level, line.rstrip('\r\n'))

	if proc.wait() != 0:
		if fail_silently:
			LOG.debug('Failed to run %s, but was told to carry on anyway' % subprocess.list2cmdline(args))
		else:
			raise ShellError(
				message = "Failed when running {command}".format(command=args[0]),
				output = output.getvalue()
			)
	return output.getvalue()

def path_to_lib():
	return path.abspath(path.join(
		__file__,
		path.pardir,
		path.pardir,
		path.pardir,
		'.template',
		'lib',
	))
