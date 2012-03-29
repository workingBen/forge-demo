import copy
import logging
import os
from os import path
from pprint import pformat

import lib

class ConfigurationError(lib.BASE_EXCEPTION):
	'''Indicates there is a problem with a command.'''
	pass
class ArgumentError(lib.BASE_EXCEPTION):
	'''Indicates we can't process the command-line overrides'''
	pass

class ToolConfig(dict):
	def __init__(self, log, defaults, arguments, targets):
		'''Hold all configuration to do with the Forge tools for this invocation.

		:param log: a logging.Logger instance
		:param defaults: default configuration read in from a file
		:type defaults: dict
		:param arguments: command-line arguments to override file settings
		:type arguments: list
		:param targets: targets we are running for
		:type targets: list
		'''
		self._deprecated = {
			"sdk": "android.sdk",
			"keystore": "android.profile.keystore",
			"storepass": "android.profile.storepass",
			"keyalias": "android.profile.keyalias",
			"keypass": "android.profile.keypass",
			"purge": "android.purge",
			"certificate": "ios.profile.developer_certificate",
			"c": "ios.profile.developer_certificate",
			"provisioning-profile": "ios.profile.provisioning_profile",
			"p": "ios.profile.provisioning_profile",
		}
		self._flag_args = [
			"android.purge",
			"general.interactive",
		]
		self._multi_value_args = [
		]
		self.log = log
		if defaults is None:
			defaults = {}
		if arguments is None:
			arguments = []
		self._targets = targets
		self._overrides = self._arguments_to_overrides(arguments)
		self._defaults = self._process_defaults(defaults)
	
	def all_config(self):
		'''
		Conflate configuration file and command-line overrides
		'''
		return self._explode_dict(dict(self._defaults, **self._overrides))

	def _is_key_arg(self, arg):
		return arg.startswith('--') or arg.startswith('-') and len(arg) == 2

	def _arguments_to_key_values(self, arguments):
		'''Transform list of command line arguments into key:(value1, value2) pairs'''
		key_values = {}
		while len(arguments) > 0:
			arg = arguments.pop(0)
			if arg.startswith('--'):
				key = arg[2:]
			elif arg.startswith('-') and len(arg) == 2:
				key = arg[1:]
			else:
				raise ArgumentError("Failed to parse command line arguments at {arg}".format(arg=arg))
			vals = self._consume_vals(arguments)
			key_values[key] = vals

		return key_values
	
	def _consume_vals(self, arguments):
		'''Eat things off the front of arguments until one starts with --'''
		result = []
		while len(arguments) > 0 and not self._is_key_arg(arguments[0]):
			result.append(arguments.pop(0))
		return result

	def _arguments_to_overrides(self, arguments):
		'''transform a list of command line arguments into fully processed,
		de-deprecated forms.

		Also does some validity checking of arguments, with attempts at reasonable error messages
		'''
		key_values = self._arguments_to_key_values(arguments)
	
		overrides = {}

		for key, values in key_values.iteritems():
			if key in self._deprecated:
				self.log.warning("--{key} is now deprecated: use --{new_key} instead!".format(
					key=key,
					new_key=self._deprecated[key],
				));
				key = self._deprecated[key]
			if key in self._flag_args:
				self._handle_flag_arg(key, values, overrides)
			else:
				self._handle_value_arg(key, values, overrides)
		return overrides
	
	def _handle_flag_arg(self, flag, values, overrides):
		'''set overrides[flag] to be our best guess at True or False, from the values'''
		if len(values) == 0:
			overrides[flag] = True
		else:
			if len(values) > 1:
				self.log.warning("Received multiple values for {flag}: using the last one".format(flag=flag))
			overrides[flag] = values[-1].lower() not in ('false', 'no', 'n')
		return overrides[flag]

	def _handle_value_arg(self, key, values, overrides):
		'''set overrides[key] to be values, respecting if they're multi-valued'''
		if len(values) < 1:
			self.log.error("{key} requires a value!".format(key=key))
			overrides[key] = None
		elif key in self._multi_value_args:
			overrides[key] = overrides.setdefault(key, []) + values
		else:
			if key in overrides or len(values) > 1:
				self.log.warning("{key} only accepts one value: using the last one".format(key=key))
			overrides[key] = values[-1]
		return overrides[key]

	@classmethod
	def _flatten_dict(cls, dct, crumbs=None):
		'Turn a hierarchy of nested dictionaries into a flat dot-separated keyspace'
		if crumbs is None:
			crumbs = []
		result = []
		
		for key, val in dct.iteritems():
			if hasattr(val, 'iteritems'):
				result += cls._flatten_dict(val, crumbs + [key])
			else:
				result.append((".".join(crumbs + [key]), val))
		return result

	@classmethod
	def _explode_dict(cls, dictionary):
		'Turn a sequence of dot-separated keys into a hierarchy'
		top_level = {}

		for key, val in dictionary.items():
			crumbs = key.split('.')

			current_level = top_level
			for crumb in crumbs[:-1]:
				if crumb not in current_level:
					current_level[crumb] = {}

				current_level = current_level[crumb]
			current_level[crumbs[-1]] = val

		return top_level

	def profile(self):
		'Return the active profile for this ToolConfig'
		specified_profile = self._overrides.get('profile')
		return "DEFAULT" if specified_profile is None else specified_profile

	def _process_defaults(self, defaults):
		'Bring the specified profile up to the <target>.profile position'
		specified_profile = self._overrides.get('profile')
		result = copy.deepcopy(defaults)

		for top_level_group in defaults:
			group = result[top_level_group]
			if not hasattr(group, 'get'):
				self.log.error("Expected to find object at {name}; found {thing}".format(
					name=top_level_group,
					thing=group,
				))
				del result[top_level_group]
				continue

			active_profile = "DEFAULT" if specified_profile is None else specified_profile

			if active_profile in group.get("profiles", {}):
				profile_val = copy.deepcopy(group["profiles"][active_profile])
				group["profile"] = profile_val
			elif top_level_group in self._targets:
				msg = "No profile {profile} found for {group_name}".format(
						profile=active_profile,
						group_name=top_level_group,
					)
				if specified_profile:
					# explicit profile requested
					raise ArgumentError(msg)
				else:
					self.log.warning(msg)
			if "profiles" in group:
				del group["profiles"]
		return dict(self._flatten_dict(result))

	def __setitem__(self, *args, **kw):
		raise NotImplementedError("{self} is immutable".format(self=self))
	def set(self, *args, **kw):
		raise NotImplementedError("{self} is immutable".format(self=self))
	def pop(self, *args, **kw):
		raise NotImplementedError("{self} is immutable".format(self=self))
	def setdefault(self, *args, **kw):
		raise NotImplementedError("{self} is immutable".format(self=self))
	def update(self, *args, **kw):
		raise NotImplementedError("{self} is immutable".format(self=self))

	def __getitem__(self, key):
		if key in self._overrides:
			value = self._overrides[key]
			self.log.debug("Using override value {value} for {key}".format(key=key, value=value))
			return value
		elif key in self._defaults:
			value = self._defaults[key]
			self.log.debug("Using configuration file value {value} for {key}".format(key=key, value=value))
			return value
		else:
			raise KeyError("No tool configuration found for key {key}: you must supply "
					"this in your local_config.json file, or as a command-line argument".format(key=key))
	def __contains__(self, key):
		return key in self._overrides or key in self._defaults
	def get(self, key, default=None):
		try:
			return self[key]
		except KeyError:
			return default
	def has_key(self, key):
		return key in self

class Build(object):
	tasks = {}
	predicates = {}
	
	def __init__(self, config, source_dir, output_dir, external=True, remove_attribution=False, usercode=None,
			ignore_patterns=None, enabled_platforms=('chrome', 'firefox', 'safari', 'ie', 'android', 'web'),
			log=None, template_only=False, test=False, forge_root=None, local_config=None, extra_args=None, **kw):
		'''Create Forge apps, according to the supplied configuration parameters.
	
		:param config: application configuration: any values which are required by the template files
		:type config: dict
		:param source_dir: directory holding the platform source
		:param output_dir: directory to which this generation process will write to
		:param external: is this a Forge build for internal debugging (i.e. un-minified for, not for customer eyes)?
		:param remove_attribution: flag to remove (built on Forge) attribution in description
		:param usercode: location of the customer's code
		:param ignore_patterns: a set of patterns that prevent certain usercode files being injected
		:param enabled_platforms: a sequence of platform names to build for
			(default: ``('chrome', 'firefox', 'safari', 'ie', 'android', 'web')``)
		:param log: a :class:`logging.Logger` instance
		:param template_only: ``True``: we just creating the platform files; ``False``
			we should also include the customer's code to create full apps
		:param test: Use the current changeset hash as the UUID
		:param forge_root: directory the Forge tools have been extracted to
		:param local_config: tool configuration read in from a local configuration file
		:param extra_args: as-yet unhandled command-line arguments
		'''
		super(Build, self).__init__()
		self.script = []
		self.log = log if log is not None else logging.getLogger(__name__)
		self.config = config
		self.source_dir = path.abspath(source_dir)
		self.output_dir = path.abspath(output_dir)
		self.external = external
		self.remove_attribution = remove_attribution
		self.usercode = usercode if usercode else path.join(self.source_dir, 'user')
		self.ignore_patterns = ignore_patterns if ignore_patterns else []
		self.log.info('enabled platforms: %s' % list(enabled_platforms))
		self.enabled_platforms = enabled_platforms
		self.template_only = template_only
		self.test = test
		self.forge_root = forge_root
		self.unpackaged = {} # will hold locations of unpackaged source trees
		self.packaged = {} # will hold locations of packaged binaries
		self.tool_config = ToolConfig(self.log, local_config, extra_args, self.enabled_platforms)
		self.orig_wd = os.getcwd()
		
	def add_steps(self, steps):
		'''Append a number of steps to the script that this runner will execute
		
		:param steps: a list of 5-tuple commands
		'''
		self.script += steps
		
	def _run_task(self, func_name, args, kw):
		'run an individual task'
		if func_name == 'debug':
			import pdb
			pdb.set_trace()
			return
		if func_name not in self.tasks:
			raise ConfigurationError("{func_name} has not been registered as a task".format(func_name=func_name))
			
		args = args or ()
		kw = kw or {}
		self.log.debug('running %s(%s, %s)' % (func_name, args, kw))
		try:
			self.tasks[func_name](self, *args, **kw)
		except Exception, e:
			self.log.error('%s while running %s(%s, %s)' % (e, func_name, args, kw))
			raise
	
	def _get_predicate_functions(self, predicate_str):
		'convert a comma-separated string of predicate names to an array of functions'
		# predicate_str can be None - meaning do in any situation
		# or a comma-separated list of predicate names to invoke
		predicate_meths = []
		if predicate_str:
			for pred_name in [p.strip() for p in predicate_str.split(',')]:
				if pred_name not in self.predicates:
					raise ConfigurationError("{pred_name} has not been registered as a predicate".format(pred_name=pred_name))
				predicate_meths.append(self.predicates[pred_name])
		return predicate_meths
	
	def _preprocess_script(self, script):
		"""Pad tuples out to 5 elements and filter by predicate and platform"""
		result = []
		for raw_command in script:
			# pad incomplete command with Nones (e.g. no kw supplied)
			# 5 is expected length: platform , predicate , func_name , (args) , {kw}
			command = list(raw_command) + [None]*(5-len(raw_command))
			platform , predicate = command[:2]
			
			# "all" platform is wildcard
			# can also configure >1 platform, comma separated, e.g. android,ios
			if platform == 'all' or (set(platform.split(',')) & set(self.enabled_platforms)):
				predicate_meths = self._get_predicate_functions(predicate)
				if all(pred(self) for pred in predicate_meths):
					result.append(tuple(command))
		return result
		
	def run(self):
		'''Processes a declarative-ish script, describing a set of commands'''
		self.log.info('{0} running...'.format(self))
		self.log.info('reading app code from %s' % self.source_dir)
		self.log.info('writing new app to %s' % self.output_dir)
		
		self.script = self._preprocess_script(self.script)
		self.log.debug('{0} script:\n{1}'.format(self, pformat(self.script)))
		
		for command in self.script:
			func_name , args , kw = command[2:]
			self._run_task(func_name, args, kw)
			
		self.log.info('{0} has finished'.format(self))
	
	def __repr__(self):
		return '<ForgeTask ({0})>'.format(", ".join(self.enabled_platforms))

