# GoTools

GoTools is a a [Sublime Text 3](http://www.sublimetext.com) plugin inspired by [vim-go](https://github.com/fatih/vim-go). Rather than attempting to reinvent various supporting IDE components, it provides integration with existing community-supported tools for the [Go programming language](http://www.golang.org).

**Please note** that the project is still considered a pre-release alpha/personal project and no effort is being made to maintain compatibility with any old settings or environments.

## Features

* Jump to symbol/declaration (using your choice of [oracle](https://godoc.org/golang.org/x/tools/oracle) or [godef](https://github.com/rogpeppe/godef))
* Format and syntax check on save, including gutter marks (using [gofmt](https://golang.org/cmd/gofmt/))
* Autocompletion (using [gocode](https://github.com/nsf/gocode))
* Build and test integration
* Source analysis (using [oracle](https://godoc.org/golang.org/x/tools/oracle))
* Improved syntax support (borrowed from [GoSublime](https://github.com/DisposaBoy/GoSublime))

### Prerequisites

GoTools will attempt to find `oracle`, `gofmt`, and `gocode` using GOPATH and GOROOT as resolved according to your GoTools settings. If you don't have these binaries, use `go get` to install them, e.g.:

    go get -u -v golang.org/x/tools/cmd/oracle
    go get -u -v github.com/nsf/gocode

GoTools is only tested with Go 1.4.

### Installing

To install on Linux:

`git clone git@github.com:ironcladlou/GoTools.git ~/.config/sublime-text-3/Packages/GoTools`

To install on OSX:

`git clone git@github.com:ironcladlou/GoTools.git ~/Library/Application\ Support/Sublime\ Text\ 3/Packages/GoTools`

### Configure GoTools

Create a GoTools settings file through the Sublime Text preferences menu at `Package Settings -> GoTools -> Settings -> User`.

[Default settings](GoTools.sublime-settings) are provided and can be accessed through the Sublime Text preferences menu at `Package Settings -> GoTools -> Settings - Default`. Each option is documented in the settings file itself.

### Configure Your Project

Create a `GoTools` settings key in a Sublime Text `.sublime-project` file (through the menu at `Project -> Edit Project`).

A documented [example project file](ExampleProject.sublime-project) is provided.

## Using GoTools

Most GoTools commands are available via the Sublime Text command palette. Open the palette when viewing a Go source file and search for "GoTools" to see what's available.

Many of the build commands are also available via the context menu.

#### Go to Definition

GoTools provides a `godef` Sublime Text command which can be bound to keys or called by other plugins. It will open the definition at the symbol under the caret in a new tab.

Here's an example `sublime-keymap` entry which executes `godef` when `<ctrl>+g` is pressed:

```json
{"keys": ["ctrl+.", "g"], "command": "godef"}
```

Here's an example `sublime-mousemap` entry which executes `godef` when `<ctrl>+<left mouse>` is pressed:

```json
{"button": "button1", "count": 1, "modifiers": ["ctrl"], "command": "godef"}
```

#### Autocomplete

Autocompletion is backed by `gocode` and integrated with Sublime Text's built-in suggestion engine.

Here's an example key binding which autocompletes when `<ctrl>+<space>` is pressed:

```json
{"keys": ["ctrl+space"], "command": "auto_complete"}
```

When `gocode` has suggestions, a specially formatted suggestion list will appear, including type information for each suggestion.

#### Go Builds

Build support is backed by `go build` and integrates with the Sublime Text build system.

Activate the GoTools build system from the Sublime Text menu by selecting it from `Tools -> Build System`. If the build system is set to `Automatic`, GoTools will be automatically used for builds when editing Go source files.

There are several ways to perform a build:
 
  * From the Sublime Text menu at `Tools -> Build`
  * A key bound to the `build` command
  * The command palette, as `Build: Build`

A `Clean Build` command variant is also provided which recursively deletes all `GOPATH/pkg` directory contents prior to executing the build as usual.

Build results are placed in the built-in Sublime Text build output panel which can be toggled with a command such as:

```json
{ "keys" : ["ctrl+m"], "command" : "show_panel" , "args" : {"panel": "output.exec", "toggle": true}},
```

#### Go Tests

Test support is backed by `go test` and is integrated with the Sublime Text build system. 

GoTools attempts to "do what you mean" depending on context. For instance, when using `Run Test at Cursor` in a test file which requires an `integration` Go build tag, GoTools will notice this and automatically add `-tags integration` to the test execution.

The following GoTools build variants are available:

  * `Run Tests` discovers test packages based on the `project_package` and `test_packages` settings relative to the project `gopath` and executes them.
  * `Run Test at Cursor` runs a single test method at or surrounding the cursor.
  * `Run Current Package Tests` runs tests for the package containing the current file.
  * `Run Tagged Tests` is like `Run Tests` but for the packages specified in the `tagged_packages` setting.
  * `Run Last Test` re-runs the last test variant that was executed.

Test results are placed in the built-in Sublime Text build output panel which can be toggled with a command such as:

```json
{ "keys" : ["ctrl+m"], "command" : "show_panel" , "args" : {"panel": "output.exec", "toggle": true}},
```

#### Oracle Analysis (experimental)

Source code analysis is backed by `oracle`. The following oracle commands are supported:

* Callers
* Callees
* Callstack
* Describe
* Freevars (requires a selection)
* Implements
* Peers
* Referrers

Use the Sublime Text command palette to run each command (try filtering with "oracle").

See the [Default.sublime-commands](Default.sublime-commands) file for the Sublime Text commands which can be mapped to keys.

Oracle results are placed in a Sublime Text output panel which can be toggled with a command such as:

```json
{ "keys" : ["ctrl+m"], "command" : "show_panel" , "args" : {"panel": "output.gotools_oracle", "toggle": true}},
```

**NOTE**: Many of the oracle commands can be extremely slow for large projects. The status bar will indicate when a command is in progress. Check the Sublime Text console logs for detailed output and troubleshooting.

### Gocode Caveats

**Important**: Using gocode support will modify the `lib-path` setting in the gocode daemon. The change will affect all clients, including other Sublime Text sessions, Vim instances, etc. Don't use this setting if you're concerned about interoperability with other tools which integrate with gocode.

Some projects make use of a dependency isolation tool such as [Godep](https://github.com/tools/godep), and many projects use some sort of custom build script. Additionally, gocode uses a client/server architecture, and at present relies on a global server-side setting to resolve Go package paths for suggestion computation. By default, gocode will only search `GOROOT` and `GOPATH/pkg` for packages, which may be insufficient if the project compiles source to multiple `GOPATH` entries (such as `Godeps/_workspace/pkg`).

With such a project, to get the best suggestions from gocode, it's necessary to configure the gocode daemon prior to client suggestion requests to inform gocode about the locations of compiled packages for the project.

GoTools will infer the correct gocode `lib-path` by constructing a path which incorporates all project `GOPATH` entries.

### GoSublime Caveats

Installing GoTools alongside GoSublime isn't tested or supported, so YMMV.
