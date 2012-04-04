# A sample Guardfile
# More info at https://github.com/guard/guard#readme

# Add files and commands to this file, like the example:
#   watch(%r{file/path}) { `command(s)` }
#
guard 'shell' do
  watch(%r{^src/(.+)}) {|m| `sed 'sX<head>X<head><script src=\'/forge/all.js\'></script>Xg' #{m[0]} > development/chrome/#{m[0]}.new && mv development/chrome/#{m[0]}.new development/chrome/#{m[0]}` }
  watch(%r{^src/(.+)}) {|m| `forge build; forge run android` }
end
