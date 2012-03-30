
from lib import predicate
import sys

@predicate
def is_external(build):
	return bool(build.external)

@predicate
def have_safari_icons(build):
	return "icons" in build.config and \
		("32" in build.config["icons"] or "32" in build.config["icons"].get("safari", {})) and \
		("48" in build.config["icons"] or "48" in build.config["icons"].get("safari", {})) and \
		("64" in build.config["icons"] or "64" in build.config["icons"].get("safari", {}))

@predicate
def have_android_icons(build):
	return "icons" in build.config and \
		("36" in build.config["icons"] or "36" in build.config["icons"].get("android", {})) and \
		("48" in build.config["icons"] or "48" in build.config["icons"].get("android", {})) and \
		("72" in build.config["icons"] or "72" in build.config["icons"].get("android", {}))

@predicate
def have_firefox_icons(build):
	return "icons" in build.config and \
		("32" in build.config["icons"] or "32" in build.config["icons"].get("firefox", {})) and \
		("64" in build.config["icons"] or "64" in build.config["icons"].get("firefox", {}))

@predicate
def have_ios_icons(build):
	return "icons" in build.config and \
		("57" in build.config["icons"] or "57" in build.config["icons"].get("ios", {})) and \
		("72" in build.config["icons"] or "72" in build.config["icons"].get("ios", {})) and \
		("114" in build.config["icons"] or "114" in build.config["icons"].get("ios", {}))

@predicate
def have_ios_launch(build):
	return "launch_images" in build.config and \
		"iphone" in build.config["launch_images"] and \
		"iphone-retina" in build.config["launch_images"] and \
		"ipad" in build.config["launch_images"] and \
		"ipad-landscape" in build.config["launch_images"]

@predicate
def have_android_launch(build):
	return "launch_images" in build.config and \
		"android" in build.config["launch_images"] and \
		"android-landscape" in build.config["launch_images"]

@predicate
def include_user(build):
	return not build.template_only

@predicate
def include_affiliate(build):
	return "libs"in build.config and \
		"affiliate" in build.config["libs"]

@predicate
def include_gmail(build):
	return "libs"in build.config and \
		"gmail" in build.config["libs"]

@predicate
def include_jquery(build):
	return "libs"in build.config and \
				"jquery" in build.config["libs"]
				
def _disable_orientation_generic(build, device, orientation):
	if not 'orientations' in build.config:
		return False
	
	if device in build.config['orientations']:
		return not build.config['orientations'][device] == orientation and not build.config['orientations'][device] == 'any'
	elif 'default' in build.config['orientations']:
		return not build.config['orientations']['default'] == orientation and not build.config['orientations']['default'] == 'any'
	else:
		return False

@predicate
def disable_orientation_iphone_portrait_up(build):
	return _disable_orientation_generic(build, 'iphone', 'portrait')
	
@predicate
def disable_orientation_iphone_portrait_down(build):
	return _disable_orientation_generic(build, 'iphone', 'portrait')

@predicate
def disable_orientation_iphone_landscape_left(build):
	return _disable_orientation_generic(build, 'iphone', 'landscape')

@predicate
def disable_orientation_iphone_landscape_right(build):
	return _disable_orientation_generic(build, 'iphone', 'landscape')

@predicate
def disable_orientation_ipad_portrait_up(build):
	return _disable_orientation_generic(build, 'ipad', 'portrait')
	
@predicate
def disable_orientation_ipad_portrait_down(build):
	return _disable_orientation_generic(build, 'ipad', 'portrait')

@predicate
def disable_orientation_ipad_landscape_left(build):
	return _disable_orientation_generic(build, 'ipad', 'landscape')

@predicate
def disable_orientation_ipad_landscape_right(build):
	return _disable_orientation_generic(build, 'ipad', 'landscape')

@predicate
def partner_parse_enabled(build):
	return "partners" in build.config and \
				"parse" in build.config["partners"] and \
				"applicationId" in build.config["partners"]["parse"] and \
				"clientKey" in build.config["partners"]["parse"]

@predicate
def partner_parse_disabled(build):
	return not partner_parse_enabled(build)

@predicate
def module_topbar_enabled(build):
	return "modules" in build.config and \
			"topbar" in build.config["modules"]

@predicate
def is_osx(build):
	return sys.platform.startswith('darwin')