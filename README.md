# GoTools

GoTools is a a [Sublime Text 3](http://www.sublimetext.com) plugin inspired by [vim-go](https://github.com/fatih/vim-go). Rather than attempting to reinvent various supporting IDE components, it provides integration with existing community-supported tools for the [Go programming language](http://www.golang.org).

**Please note** that the project is still considered a pre-release alpha/personal project and no effort is being made to maintain compatibility with any old settings or environments.

## Features

* Jump to symbol/declaration with [godef](http://godoc.org/code.google.com/p/rog-go/exp/cmd/godef).
* Format and syntax check on save with [gofmt](http://godoc.org/code.google.com/p/go.tools/cmd/gofmt).
* Autocompletion support using [gocode](https://github.com/nsf/gocode).
* Build and test integration.
* Improved syntax support (borrowed from [GoSublime](https://github.com/DisposaBoy/GoSublime)).


## Installation

The plugin assumes all supporting binaries are located in `go_bin_path` as defined in the settings. Use `go get` to install them, e.g.:

    go get -v code.google.com/p/rog-go/exp/cmd/godef
    go get -v code.google.com/p/go.tools/cmd/gofmt
    go get -v github.com/nsf/gocode

To install the plugin (TODO: Package Control support):

#### OSX

    git clone git@github.com:ironcladlou/GoTools.git ~/Library/Application\ Support/Sublime\ Text\ 3/Packages/GoTools

#### Linux

    git clone git@github.com:ironcladlou/GoTools.git ~/.config/sublime-text-3/Packages/GoTools

## Getting Started

Create a GoTools settings file through the Sublime Text preferences menu using `Package Settings -> GoTools -> Settings -> User`. A an example settings file is provided by `Package Settings -> GoTools -> Settings - Default`.

```
{
  // All go tools other than go itself will be executed from this directory. Required.
  "go_bin_path": "/home/user/go/bin",

  // The global GOPATH to use for go tool executions. Available in project settings
  // "gopath" values as ${gopath}. Required.
  "gopath": "/home/user/go",

  // The go installation directory. Required.
  "goroot": "/usr/lib64/golang",

  // The go architecture to use for package resolution. Required.
  "goarch": "amd64",

  // The go OS to use for package resolution. Required.
  "goos": "linux",

  // Enable gofmt formatting after a file is saved. Optional.
  "gofmt_enabled": true,

  // Instead of `gofmt`, use another command (e.g. goimports). Optional.
  "gofmt_cmd": "gofmt",

  // Enable gocode autocompletion support. Optional.
  "gocode_enabled": true,

  // Enable GoTools console debug output. Optional.
  "debug_enabled": false,

  // Use GoTools for all *.go files
  "extensions": ["go"]
}
```

Create a GoTools settings key in a Sublime Text `.sublime-project` file (using the `Project -> Edit Project` menu).

Here's an example `.sublime-project` which uses a `GOPATH` override and integrates with the GoTools build system:

```
{
  "folders": [],
  "settings": {
    "GoTools": {
      // A custom GOPATH for this project; ${gopath} is replaced by the global value.
      "gopath": "${gopath}/src/github.com/some/project/Godeps/_workspace:${gopath}",

      // The root package (or namespace) of a project.
      "project_package": "github.com/some/project",

      // A list of sub-packages relative to project_packages to be included in builds.
      "build_packages": ["cmd/myprogram"],

      // A list of sub-packages relative to project_package to be included in test
      // discovery.
      "test_packages": ["cmd", "lib", "examples"]
    }
  }
}
```

## Using GoTools

### Go to definition

GoTools provides a `godef` Sublime Text command which can be bound to keys or called by other plugins.

Here's an example key binding:

    { "keys" : ["ctrl+.", "g"], "command": "godef" }

Now pressing `<ctrl> . g` with the cursor on a symbol will jump the cursor to its definition in a new tab.

### Autocompletion

Autocompletion is provided by Sublime Text's built-in suggestion engine, and is backed by `gocode`. Here's an example key binding:

    { "keys": ["ctrl+space"], "command": "auto_complete" }

When `gocode` has suggestions, a specially formatted suggestion list will appear, including type information for each suggestion.

### Go builds

Build support is provided through the Sublime Text build system and is backed by `go build`.

Activate the GoTools build system from the Sublime Text menu by selecting it from `Tools -> Build System`. If the build system is set to `Automatic`, GoTools will be automatically selected when editing files matching `*.go`

There are many ways to perform a build:
 
  * From the Sublime Text menu at `Tools -> Build`
  * A hotkey bound to the `build` command
  * The command palette, as `Build: Build`

A `Clean Build` variant is also provided which recursively deletes all `GOPATH/pkg` directory contents prior to executing the build as usual.

### Go tests

Test support is provided as build variants via the GoTools build system, and is backed by `go test`.

The following GoTools build variants allow a variety of test executions:

  * `Run Tests` discovers test packages based on the `project_package` and `test_packages` settings relative to the project `gopath` and executes them.
  * `Run Test at Cursor` runs a single test method at or surrounding the cursor.
  * `Run Current Package Tests` runs tests for the package containing the current file.

## Notes

#### Gocode support considerations

**Important**: Using gocode support will modify the `lib-path` setting in the gocode daemon. The change will affect all clients, including other Sublime Text sessions, Vim instances, etc. Don't use this setting if you're concerned about interoperability with other tools which integrate with gocode.

Some projects make use of a dependency isolation tool such as [Godep](https://github.com/tools/godep), and many projects use some sort of custom build script. Additionally, gocode uses a client/server architecture, and at present relies on a global server-side setting to resolve Go package paths for suggestion computation. By default, gocode will only search `GOROOT` and `GOPATH/pkg` for packages, which may be insufficient if the project compiles source to multiple `GOPATH` entries (such as `Godeps/_workspace/pkg`).

With such a project, to get the best suggestions from gocode, it's necessary to configure the gocode daemon prior to client suggestion requests to inform gocode about the locations of compiled packages for the project.

GoTools will infer the correct gocode `lib-path` by constructing a path using the `goroot`, `goarch`, `goos`, and `gopath` settings entries. For gocode support to work as expected, it's important to set each of those values in the settings.

#### Using with GoSublime

Installing GoTools alongside GoSublime isn't tested or supported, so YMMV.
