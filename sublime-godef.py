import sublime, sublime_plugin, subprocess, os, locale

class GodefCommand(sublime_plugin.WindowCommand):
  def run(self):
    # Load custom settings
    settings = sublime.load_settings("sublime-godef.sublime-settings")
    self.gopath = settings.get("gopath", os.getenv('GOPATH'))

    # Validate GOPATH
    if self.gopath is None:
      self.log("ERROR: no GOPATH defined")
      return

    self.log("using gopath " + self.gopath)

    # Find and store the current filename and byte offset at the
    # cursor location
    view = self.window.active_view()
    row, col = view.rowcol(view.sel()[0].begin())

    self.offset = view.text_point(row, col)
    self.filename = view.file_name()

    # Execute the command asynchronously    
    sublime.set_timeout_async(self.godef, 0)

  def godef(self):
    godef_bin = os.path.join(self.gopath, "bin", "godef")

    if not os.path.isfile(godef_bin):
      self.log("ERROR: godef not found at " + godef_bin)
      return

    try:
      args = [godef_bin, "-f", self.filename, "-o", str(self.offset)]
      self.log("spawning " + " ".join(args))

      env = os.environ.copy()
      env["GOPATH"] = self.gopath
      output = subprocess.check_output(args, stderr=subprocess.STDOUT, env=env)
    except subprocess.CalledProcessError as e:
      self.log("no definition found")
    else:
      location = output.decode("utf-8").rstrip().split(":")

      # godef is sometimes returning this junk as part of the output,
      # so just scrub it away
      file = location[0].replace("importer=0xa0d80", "")
      row = int(location[1])
      col = int(location[2])

      if not os.path.isfile(file):
        self.log("ERROR: file indicated by godef not found: " + file)
        return

      self.log("opening definition at " + file + ":" + str(row) + ":" + str(col))
      view = self.window.open_file(file)
      sublime.set_timeout(lambda: self.show_location(view, row, col), 10)

  def show_location(self, view, row, col, retries=0):
    if not view.is_loading():
      pt = view.text_point(row-1, 0)
      view.sel().clear()
      view.sel().add(sublime.Region(pt))
      view.show(pt)
    else:
      if retries < 10:
        sublime.status_message('sublime-godef: waiting for file to load...')
        sublime.set_timeout(lambda: self.show_location(view, row, col, retries+1), 10)
      else:
        sublime.status_message("sublime-godef: timed out waiting for file load")
        self.log("ERROR: timed out waiting for file load - giving up")

  def log(self, msg):
    print("sublime-godef: " + msg)