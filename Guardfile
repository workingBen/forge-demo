# A sample Guardfile
# More info at https://github.com/guard/guard#readme

# Add files and commands to this file, like the example:
#   watch(%r{file/path}) { `command(s)` }
#
guard 'shell' do
  watch(%r{^src/(.+)}) {|m| `sed 's/<head>/<head><script src="\/forge\/all.js"><\/script>/g' #{m[0]} > #{m[0]}.new && mv #{m[0]}.new development/chrome/#{m[0]}` }
end
