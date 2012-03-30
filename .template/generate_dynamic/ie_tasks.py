from os import path
import shutil, glob
from subprocess import Popen, PIPE, STDOUT

from lib import cd, CouldNotLocate, task

class IEError(Exception):
	pass

@task
def package_ie(build, root_dir, **kw):
	'Run NSIS'
	
	nsis_check = Popen('makensis -VERSION', shell=True, stdout=PIPE, stderr=STDOUT)
	stdout, stderr = nsis_check.communicate()
	
	if nsis_check.returncode != 0:
		raise CouldNotLocate("Make sure the 'makensis' executable is in your path")
	
	# JCB: need to check nsis version in stdout here?
	
	with cd(path.join(root_dir, 'ie')):
		for arch in ('x86', 'x64'):
			nsi_filename = "setup-{arch}.nsi".format(arch=arch)
			
			package = Popen('makensis {nsi}'.format(nsi=path.join("dist", nsi_filename)),
				stdout=PIPE, stderr=STDOUT, shell=True
			)
		
			out, err = package.communicate()
		
			if package.returncode != 0:
				raise IEError("problem running {arch} IE build: {stdout}".format(arch=arch, stdout=out))
			
			# move output to root of IE directory
			for exe in glob.glob(path.join("dist/*.exe")):
				shutil.move(exe, "{name}-{version}-{arch}.exe".format(
					name=build.config.get('name', 'Forge App'),
					version=build.config.get('version', '0.1'),
					arch=arch
				))