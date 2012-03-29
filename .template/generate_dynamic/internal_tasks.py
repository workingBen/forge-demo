import logging
import json

LOG = logging.getLogger(__name__)

_invalidating_config_keys = {
		"author": True,
		"description": True,
		"platform_version": True,
		"version": True,
		"package_names": True,
		"activations": True,
		"background_files": True,
		"libs": True,
		"browser_action": True,
		"permissions": True,
		"update_url": True,
		"logging": True,
		"parameters": True,
		"homepage": True,
		"orientations": True,
		"partners": True,
		"modules": True,
}

def config_changes_invalidate_templates(generate, old_config_filename, new_config_filename):
	with open(old_config_filename) as old_config_file:
		old_config = old_config_file.read()
	with open(new_config_filename) as new_config_file:
		new_config = new_config_file.read()
	
	try:
		current_filename = old_config_filename
		old_config_d = json.loads(old_config)
		current_filename = new_config_filename
		new_config_d = json.loads(new_config)
	except Exception as e:
		raise generate.lib.BASE_EXCEPTION("{file} is not valid JSON: {msg}".format(
			file=current_filename,
			msg=e,
		))
	
	if old_config_d == new_config_d:
		LOG.debug("configuration is identical to last run")
		return False

	for key in _invalidating_config_keys:
		if old_config_d.get(key) != new_config_d.get(key):
			LOG.debug("'{key}' has changed in configuration".format(key=key))
			return True
	
	LOG.debug("configuration has not changed")
	return False
