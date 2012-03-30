'''Goals are a collection of phases which are automatically added to a build, then executed.

The idea here is for the calling code to not need to know about the right phases to include
when getting a higher-level "goal" done; e.g. running or generating an app.
'''
import platform
import sys

from lib import BASE_EXCEPTION

# TODO: schema file for local_config.json

def log_build(build, action):
	'''
	Bundle together some stats and send it to the server for tracking
	This is called by every other function in this module, just before running
	the build.
	'''
	from forge import build_config
	import forge
	from forge.remote import Remote

	log = {}
	log['action']        = action
	log['platform']      = platform.platform()
	log['version']       = sys.version
	log['uuid']          = build.config['uuid']
	log['tools_version'] = forge.VERSION
	config = build_config.load()
	remote = Remote(config)
	remote._authenticate()
	remote._api_post('track/', data=log)

def generate_app_from_template(generate_module, build_to_run, server=False):
	'''Inject code into a previously built template.
	
	:param generate_module: the :mod:`generate.generate` module
	:param build_to_run: a :class:`build.Build` instance
	:param server: are we running on the server context or on a customer's machine
	'''
	add_check_settings_steps(generate_module, build_to_run)
	build_to_run.add_steps(generate_module.customer_phases.resolve_urls())
	build_to_run.add_steps(generate_module.customer_phases.copy_user_source_to_template(server=server, ignore_patterns=build_to_run.ignore_patterns))
	build_to_run.add_steps(generate_module.customer_phases.include_platform_in_html(server=server))
	build_to_run.add_steps(generate_module.customer_phases.include_icons())
	build_to_run.add_steps(generate_module.customer_phases.include_name())
	build_to_run.add_steps(generate_module.customer_phases.make_installers(build_to_run.output_dir))

	log_build(build_to_run, "generate")
	build_to_run.run()

def run_app(generate_module, build_to_run, server=False):
	'''Run a generated app on a device or emulator.
	
	:param generate_module: the :mod:`generate.generate` module
	:param build_to_run: a :class:`build.Build` instance
	:param server: are we running on the server context or on a customer's machine
	'''
	add_check_settings_steps(generate_module, build_to_run)

	if len(build_to_run.enabled_platforms) != 1:
		raise BASE_EXCEPTION("Expected to run exactly one platform at a time")

	target = list(build_to_run.enabled_platforms)[0]
	if target == 'android':
		interactive = build_to_run.tool_config.get('general.interactive', True)
		sdk = build_to_run.tool_config.get('android.sdk')
		device = build_to_run.tool_config.get('android.device')
		purge = build_to_run.tool_config.get('android.purge')

		build_to_run.add_steps(
			generate_module.customer_phases.run_android_phase(
				build_to_run.output_dir,
				sdk=sdk,
				device=device,
				interactive=interactive,
				purge=purge,
			)
		)
	elif target == 'ios':
		device = build_to_run.tool_config.get('ios.device')

		build_to_run.add_steps(
			generate_module.customer_phases.run_ios_phase(device)
		)
	elif target == 'firefox':
		build_to_run.add_steps(
			generate_module.customer_phases.run_firefox_phase(build_to_run.output_dir)
		)
	elif target == 'web':
		build_to_run.add_steps(
			generate_module.customer_phases.run_web_phase()
		)
	
	log_build(build_to_run, "run")
	build_to_run.run()

def package_app(generate_module, build_to_run, server=False):
	add_check_settings_steps(generate_module, build_to_run)

	if len(build_to_run.enabled_platforms) != 1:
		raise BASE_EXCEPTION("Expected to package exactly one platform at a time")

	build_to_run.add_steps(
		generate_module.customer_phases.package(build_to_run.output_dir)
	)
	log_build(build_to_run, "package")
	build_to_run.run()

def add_check_settings_steps(generate_module, build_to_run):
	"""
	Required steps to sniff test the JavaScript and local configuration
	"""
	build_to_run.add_steps(generate_module.customer_phases.check_javascript())
	build_to_run.add_steps(generate_module.customer_phases.check_local_config_schema())

def check_settings(generate_module, build_to_run):
	"""
	Check the validity of locally configured settings.
	"""
	add_check_settings_steps(generate_module, build_to_run)

	build_to_run.run()

def cleanup_after_interrupted_run(generate_module, build_to_run, server=False):
	"""
	Cleanup after a run operation that was interrupted forcefully.

	This is exposed so the Trigger Toolkit can cleanup anything lingering from a run operation,
	e.g. node, adb, and any locks they have on files in the development folder
	"""
	build_to_run.add_steps(generate_module.customer_phases.clean_phase())
	build_to_run.run()
