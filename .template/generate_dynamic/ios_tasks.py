import codecs
import datetime
from glob import glob
import logging
import os
from os import path
import plistlib
import re
import subprocess
import tempfile
import time
import uuid

import lib
from lib import task, read_file_as_str
from utils import run_shell

LOG = logging.getLogger(__name__)

SIMULATOR_IN_42 = "/Developer/Platforms/iPhoneSimulator.platform/Developer/Applications/iPhone Simulator.app/"
SIMULATOR_IN_43 = "/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/Applications/iPhone Simulator.app"

class IOSError(lib.BASE_EXCEPTION):
	pass

def _copy(item, into):
	# XXX not platform agnostic!
	if item[-1] == '/':
		item = item[:-1]
	run_shell('/bin/cp', '-Rp', item, into)
			
class IOSRunner(object):
	def __init__(self, path_to_ios_build):
		# TODO: should allow us to cd straight to where the ios build is
		# at the moment this points one level above, e.g. my-app/development,
		# NOT my-app/development/ios
		self.path_to_ios_build = path_to_ios_build

		self.log_process = None

	@staticmethod
	def get_child_processes(target_parent_pid):
		'Gets processes which have the given pid as their parent'
		# scrape processes for those with the iphone simulator as the parent
		list_processes = subprocess.Popen('ps ax -o "pid= ppid="', shell=True, stdout=subprocess.PIPE)

		child_pids = []

		for line in list_processes.stdout:
			line = line.strip()
			if line != "":
				pid, parent_pid = map(int, line.split())
				if parent_pid == target_parent_pid:
					child_pids.append(pid)

		return child_pids

	def _grab_plist_from_binary_mess(self, file_path):
		start_marker = '<?xml version="1.0" encoding="UTF-8"?>'
		end_marker = '</plist>'
		
		with open(file_path, 'rb') as plist_file:
			plist = plist_file.read()
		start = plist.find(start_marker)
		end = plist.find(end_marker)
		if start < 0 or end < 0:
			raise ValueError("{0} does not appear to be a valid provisioning profile".format(file_path))
		
		real_plist = plist[start:end+len(end_marker)]
		return real_plist
	
	def _parse_plist(self, plist):
		return plistlib.readPlistFromString(plist)
		
	def _extract_seed_id(self, plist_dict):
		'E.g. "DEADBEEDAA" from provisioning profile plist including "DEADBEEDAA.*"'
		app_ids = plist_dict["ApplicationIdentifierPrefix"]
		if not app_ids:
			raise ValueError("Couldn't find an 'ApplicationIdentifierPrefix' entry in your provisioning profile")
		return app_ids[0]

	def _extract_app_id(self, plist_dict):
		'E.g. "DEADBEEFAA.io.trigger.forge.app" from provisioning profile plist, only works for distribution profiles'
		entitlements = plist_dict["Entitlements"]
		if not entitlements:
			raise ValueError("Couldn't find an 'Entitlements' entry in your provisioning profile")
		app_id = entitlements['application-identifier']
		if not app_id:
			raise ValueError("Couldn't find an 'application-identifier' entry in your provisioning profile")
		return app_id
	
	def _is_distribution_profile(self, plist_dict):
		'See if the profile as any ProvisionedDevices, if not it is distribution'
		return 'ProvisionedDevices' not in plist_dict

	def _check_for_codesign(self):
		which_codesign = subprocess.Popen(['which', 'codesign'], stdout=subprocess.PIPE)
		stdout, stderr = which_codesign.communicate()
		
		if which_codesign.returncode != 0:
			raise IOError("Couldn't find the codesign command. Make sure you have xcode installed and codesign in your PATH.")
		return stdout.strip()

	def get_bundled_ai(self, plist_dict, path_to_ios_build):
		'''
		returns the application identifier, with bundle id
		'''
		# biplist import must be done here, as in the server context, biplist doesn't exist
		import biplist
		
		info_plist_path = glob(path_to_ios_build + '/ios' + '/device-*')[0] + '/Info.plist'
		return "%s.%s" % (
			plist_dict['ApplicationIdentifierPrefix'][0],
			biplist.readPlist(info_plist_path)['CFBundleIdentifier']
		)

	def check_plist_dict(self,plist_dict, path_to_ios_build):
		'''
		Raises an IOSError on:
		 - Expired profile
		 - Ad-Hoc profile
		 - invalid Entitlements
		'''
		if plist_dict['ExpirationDate'] < datetime.datetime.now():
			raise IOSError("Provisioning profile has expired")
			
		if (not plist_dict['Entitlements']['get-task-allow']) and \
			(len(plist_dict.get('ProvisionedDevices', [])) > 0):
			raise IOSError("Ad-hoc profiles are not supported")
		
		ai = plist_dict['Entitlements']['application-identifier']
		
		bundled_ai = self.get_bundled_ai(plist_dict, path_to_ios_build)
		wildcard_ai = "%s.*" % plist_dict['ApplicationIdentifierPrefix'][0]
		
		if ai == bundled_ai:
			LOG.debug("Application ID in app and provisioning profile match")
		elif ai == wildcard_ai:
			LOG.debug("Provisioning profile has valid wildcard application ID")
		else:
			raise IOSError('Provisioning profile and application ID do not match \n '
				'Provisioning profile ID: {pp_id}\n '
				'Application ID: {app_id}\n '
				'Please see "Preparing your apps for app stores" in our docs: http://docs.trigger.io/'.format(
					pp_id=bundled_ai,
					app_id=ai,
				)
			)
		
	def log_profile(self, plist_dict):
		'''
		Logs:
		name
		number of enabled devices (with ids)
		appstore profile or development
		'''
		if len(plist_dict.get('ProvisionedDevices', [])) > 0:
			
			LOG.info(str(len(plist_dict['ProvisionedDevices'])) + ' Provisioned Device(s):')
			LOG.info(plist_dict['ProvisionedDevices'])
		else:
			LOG.info('No Provisioned Devices, profile is Appstore')
	
	def _sign_app(self, build, provisioning_profile, certificate, entitlements_file):
		app_folder_name = self._locate_ios_app(error_message="Couldn't find iOS app in order to sign it")
		path_to_app = path.abspath(path.join(self.path_to_ios_build, 'ios', app_folder_name))
		codesign = self._check_for_codesign()
		embedded_profile = 'embedded.mobileprovision'
		path_to_embedded_profile = path.abspath(path.join(path_to_app, embedded_profile))
		resource_rules = path.abspath(path.join(path_to_app, 'ResourceRules.plist'))

		path_to_pp = path.join(build.orig_wd, provisioning_profile)
		if not path.isfile(path_to_pp):
			raise IOSError("{path} is not a provisioning_profile: "
					"use the --ios.profile.provisioning_profile option".format(
					path=path_to_pp)
			)

		try:
			os.remove(path_to_embedded_profile)
		except Exception:
			LOG.warning("Couldn't remove {profile}".format(profile=path_to_embedded_profile))
		_copy(path_to_pp, path_to_embedded_profile)

		run_shell(codesign, '--force', '--preserve-metadata',
				'--entitlements', entitlements_file,
				'--sign', certificate,
				'--resource-rules={0}'.format(resource_rules),
				path_to_app)


	def create_ipa_from_app(self, build, provisioning_profile, certificate_to_sign_with=None, relative_path_to_itunes_artwork=None):
		"""Create an ipa from an app, with an embedded provisioning profile provided by the user, and 
		signed with a certificate provided by the user.

		:param build: instance of build
		:param provisioning_profile: Absolute path to the provisioning profile to embed in the ipa
		:param certificate_to_sign_with: (Optional) The name of the certificate to sign the ipa with
		:param relative_path_to_itunes_artwork: (Optional) A path to a 512x512 png picture for the App view in iTunes.
			This should be relative to the location of the user assets.
		"""
		# XXX
		# TODO: refactor _copy and _replace_in_file into common utility file
		def _replace_in_file(filename, find, replace):
			tmp_file = uuid.uuid4().hex
			in_file_contents = read_file_as_str(filename)
			in_file_contents = in_file_contents.replace(find, replace)
			with codecs.open(tmp_file, 'w', encoding='utf8') as out_file:
				out_file.write(in_file_contents)
			os.remove(filename)
			os.rename(tmp_file, filename)

		LOG.info('Starting package process for iOS')
		
		if certificate_to_sign_with is None:
			certificate_to_sign_with = 'iPhone Developer'

		file_name = "{name}-{time}.ipa".format(
			name=re.sub("[^a-zA-Z0-9]", "", build.config["name"].lower()),
			time=str(int(time.time()))
		)
		output_path_for_ipa = path.abspath(path.join('release', 'ios', file_name))
		directory = path.dirname(output_path_for_ipa)
		if not path.isdir(directory):
			os.makedirs(directory)

		app_folder_name = self._locate_ios_app(error_message="Couldn't find iOS app in order to sign it")
		path_to_template_app = path.abspath(path.join(self.path_to_ios_build, '..', '.template', 'ios', app_folder_name))
		path_to_app = path.abspath(path.join(self.path_to_ios_build, 'ios', app_folder_name))
		
		# Verify current signature
		codesign = self._check_for_codesign()
		run_shell(codesign, '--verify', '-vvvv', path_to_template_app)
		
		LOG.info('going to package: %s' % path_to_app)
		
		plist_str = self._grab_plist_from_binary_mess(provisioning_profile)
		plist_dict = self._parse_plist(plist_str)
		self.check_plist_dict(plist_dict, self.path_to_ios_build)
		LOG.info("Plist OK.")
		
		self.log_profile(plist_dict)
		
		seed_id = self._extract_seed_id(plist_dict)
		
		LOG.debug("extracted seed ID: {0}".format(seed_id))
		
		temp_dir = tempfile.mkdtemp()
		with lib.cd(temp_dir):
			LOG.debug('Moved into tempdir: %s' % temp_dir)
			LOG.debug('Making Payload directory')
			os.mkdir('Payload')

			path_to_payload = path.abspath(path.join(temp_dir, 'Payload'))
			path_to_payload_app = path.abspath(path.join(path_to_payload, app_folder_name))

			if relative_path_to_itunes_artwork is not None:
				path_to_itunes_artwork = path.join(path_to_payload_app, 'assets', 'src', relative_path_to_itunes_artwork)
			else:
				path_to_itunes_artwork = None

			if self._is_distribution_profile(plist_dict):
				bundle_id = self._extract_app_id(plist_dict)
				_copy(path.join(self._lib_path(), 'template.entitlements'), temp_dir)
				_replace_in_file(path.join(temp_dir, 'template.entitlements'), 'APP_ID', bundle_id)
				self._sign_app(build=build,
						provisioning_profile=provisioning_profile,
						certificate=certificate_to_sign_with,
						entitlements_file=path.join(temp_dir, 'template.entitlements'),
					)
			else:
				self._sign_app(build=build,
						provisioning_profile=provisioning_profile,
						certificate=certificate_to_sign_with,
						entitlements_file=path.join(self._lib_path(), 'dev.entitlements'),
				)
			_copy(path_to_app, path_to_payload)
			
			if path_to_itunes_artwork:
				_copy(path_to_itunes_artwork, path.join(temp_dir, 'iTunesArtwork'))

			run_shell('/usr/bin/zip', '--symlinks', '--verbose', '--recurse-paths', output_path_for_ipa, '.')
		LOG.info("created IPA: {output}".format(output=output_path_for_ipa))
		return output_path_for_ipa

	def _locate_ios_app(self, error_message):
		ios_build_dir = path.join(self.path_to_ios_build, 'ios')
		with lib.cd(ios_build_dir):
			possible_apps = glob('device-*.app/')

			if not possible_apps:
				raise IOError(error_message)

			return possible_apps[0]
	
	def run_iphone_simulator(self):
		possible_app_location = '{0}/ios/simulator-*/'.format(self.path_to_ios_build)
		LOG.debug('Looking for apps at {0}'.format(possible_app_location))
		possible_apps = glob(possible_app_location)
		if not possible_apps:
			raise IOSError("Couldn't find iOS app to run it in the simulator")
		
		path_to_app = possible_apps[0]
		
		LOG.debug('trying to run app %s' % path_to_app)

		if path.exists(SIMULATOR_IN_42):
			LOG.debug("detected XCode version 4.2 or older")
			ios_sim_binary = "ios-sim-xc4.2"
		elif path.exists(SIMULATOR_IN_43):
			LOG.debug("detected XCode version 4.3 or newer")
			ios_sim_binary = "ios-sim-xc4.3"
		else:
			raise IOSError("Couldn't find iOS simulator in {old} or {new}".format(
				old=SIMULATOR_IN_42,
				new=SIMULATOR_IN_43,
			))
		logfile = tempfile.mkstemp()[1]
		subprocess.Popen([path.join(self._lib_path(), ios_sim_binary), "launch", path_to_app, '--stderr', logfile])
		LOG.info('Showing log output:')
		try:
			run_shell("tail", "-f", logfile, fail_silently=False, command_log_level=logging.INFO)
		finally:
			os.remove(logfile)
	
	def run_idevice(self, build, device, provisioning_profile, certificate):
		possible_app_location = '{0}/ios/device-*/'.format(self.path_to_ios_build)
		LOG.debug('Looking for apps at {0}'.format(possible_app_location))
		possible_apps = glob(possible_app_location)
		if not possible_apps:
			raise IOSError("Couldn't find iOS app to run on a device")
		
		path_to_app = possible_apps[0]

		LOG.debug("signing {app}".format(app=path_to_app))
		self._sign_app(build=build,
			provisioning_profile=provisioning_profile,
			certificate=certificate,
			entitlements_file=path.join(self._lib_path(), 'dev.entitlements'),
		)
		
		fruitstrap = [path.join(self._lib_path(), 'fruitstrap'), path_to_app]
		if device and device.lower() != 'device':
			# pacific device given
			fruitstrap.append(device)
			LOG.info('installing app on device {device}: is it connected?'.format(device=device))
		else:
			LOG.info('installing app on device: is it connected?')

		run_shell(*fruitstrap, fail_silently=False, command_log_level=logging.INFO)
		LOG.info("We can't show log output from your device here: please see the 'Console' section"
				" in the XCode Organiser view")
	
	def _lib_path(self):
		return path.abspath(path.join(
			self.path_to_ios_build,
			path.pardir,
			'.template',
			'lib',
		))

@task
def run_ios(build, device):
	runner = IOSRunner(path.abspath('development'))

	if not device or device.lower() == 'simulator': 
		LOG.info('Running iOS Simulator')
		runner.run_iphone_simulator()
	else:
		LOG.info('Running on iOS device: {device}'.format(device=device))
		certificate_to_sign_with = build.tool_config.get('ios.profile.developer_certificate', 'iPhone Developer')
		provisioning_profile = build.tool_config['ios.profile.provisioning_profile']
		if not provisioning_profile:
			raise IOSError("You must specify a provisioning profile: "
					"see http://current-docs.trigger.io/command-line.html#local-conf-ios")

		runner.run_idevice(
				build=build,
				device=device, provisioning_profile=provisioning_profile,
				certificate=certificate_to_sign_with,
		)

@task
def package_ios(build):
	provisioning_profile = build.tool_config['ios.profile.provisioning_profile']
	if not provisioning_profile:
		raise IOSError("You must specify a provisioning profile: "
				"see http://current-docs.trigger.io/command-line.html#local-conf-ios")
	certificate_to_sign_with = build.tool_config.get('ios.profile.developer_certificate', 'iPhone Developer') 

	runner = IOSRunner(path.abspath('development'))
	try:
		relative_path_to_itunes_artwork = build.config['icons']['ios']['512']
	except KeyError:
		relative_path_to_itunes_artwork = None

	runner.create_ipa_from_app(
		build=build,
		provisioning_profile=provisioning_profile,
		certificate_to_sign_with=certificate_to_sign_with,
		relative_path_to_itunes_artwork=relative_path_to_itunes_artwork,
	)

def _generate_package_name(build):
	if "package_names" not in build.config:
		build.config["package_names"] = {}
	if "ios" not in build.config["package_names"]:
		build.config["package_names"]["ios"] = "io.trigger.forge"+build.config["uuid"]
	return build.config["package_names"]["ios"]
