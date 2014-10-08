# GoTools

GoTools is a a [Sublime Text 3](http://www.sublimetext.com) plugin inspired by [vim-go](https://github.com/fatih/vim-go). Rather than attempting to reinvent various supporting IDE components, it provides integration with existing community-supported tools for the [Go programming language](http://www.golang.org).

**Please note** that the project is still considered a pre-release alpha/personal project and no effort is being made to maintain compatibility with any old settings or environments.

## Features

* Jump to symbol/declaration with [godef](http://godoc.org/code.google.com/p/rog-go/exp/cmd/godef).
* Format on save with [gofmt](http://godoc.org/code.google.com/p/go.tools/cmd/gofmt).
* Syntax errors in an output panel with navigation support.
* Autocompletion support using [gocode](https://github.com/nsf/gocode).
* Improved syntax highlighting using the `tmLanguage` support from [GoSublime](https://github.com/DisposaBoy/GoSublime).
* Build and unit test integration

## Installation

The plugin assumes all supporting binaries are located in `go_bin_path` defined in the settings. Use `go get` to install them, e.g.:

    go get -v code.google.com/p/rog-go/exp/cmd/godef
    go get -v code.google.com/p/go.tools/cmd/gofmt
    go get -v github.com/nsf/gocode

Then install the plugin manually (TODO: Package Control support):

#### OSX
    git clone git@github.com:ironcladlou/GoTools.git ~/Library/Application\ Support/Sublime\ Text\ 3/Packages/GoTools

#### Linux

    git clone git@github.com:ironcladlou/GoTools.git ~/.config/sublime-text-3/Packages/GoTools

## Getting Started

Access the default and user specified settings via the `Package Settings -> GoTools` menu in Sublime Text. The `gopath` and `go_bin_path` settings are required. Here's an example user settings file:

```json
{
  "go_bin_path": "/home/ironcladlou/go/bin",
  "gopath": "/home/ironcladlou/go",
  "goroot": "/usr/lib64/golang",
  "goarch": "amd64",
  "goos": "linux",
  "gofmt_enabled": true,
  "gofmt_cmd": "gofmt",
  "gocode_enabled": true
}
```

Next, integrate GoTools with a Sublime Text project by adding a `GoTools` settings entry to a project's `.sublime-project` file.

Here's an example project file which uses a `GOPATH` override and integrates with the GoTools build system:

```json
{
  "folders": [],
  "settings": {
    "GoTools": {
      "gopath": "/home/ironcladlou/go/src/github.com/some/project/Godeps/_workspace:${gopath}",
      "project_package": "github.com/some/project",
      "build_package": "github.com/some/project/cmd/myprogram",
      "test_packages": ["cmd", "lib", "examples"]
    }
  }
}
```

Any occurence of `${gopath}` in the `gopath` setting will be automatically replaced with the `gopath` value from the `GoTools.sublime-settings` file.

## Using GoTools

### Go to definition

GoTools provides a `godef` Sublime Text command which can be bound to keys or called by other plugins.

Here's an example key binding:

    { "keys" : ["ctrl+'", "g"], "command": "godef" }


### Build system

GoTools provides a `GoTools` Sublime Text build system which integrates with GoTools settings to run `go build` and `go install`.

The build system discovers packages to build and test based on GoTools settings.

To build, execute the `GoTools` build system using Sublime Text's built-in support. In addition to the main build type, the `GoTool` build system provides two variants:

  * `Clean Build` recursively deletes all `GOPATH/pkg` directory contents and then executes a build.
  * `Run Unit Tests` discovers test packages based on the `project_package` and `test_packages` settings relative to the project `GOPATH` and executes them.

These can be executed from the command pallette or bound to keys like any other build system variant.


### Syntax support

To use the Sublime Text syntax support, select `Go (GoTools)` from the `View -> Syntax` menu.

## Notes

#### Gocode support considerations

**Important**: Using gocode support will modify the `lib-path` setting in the gocode daemon. The change will affect all clients, including other Sublime Text sessions, Vim instances, etc. Don't use this setting if you're concerned about interoperability with other tools which integrate with gocode.

Some projects make use of a dependency isolation tool such as [Godep](https://github.com/tools/godep), and many projects use some sort of custom build script. Additionally, gocode uses a client/server architecture, and at present relies on a global server-side setting to resolve Go package paths for suggestion computation. By default, gocode will only search `GOROOT` and `GOPATH/pkg` for packages, which may be insufficient if the project compiles source to multiple `GOPATH` entries (such as `Godeps/_workspace/pkg`).

With such a project, to get the best suggestions from gocode, it's necessary to configure the gocode daemon prior to client suggestion requests to inform gocode about the locations of compiled packages for the project.

GoTools will infer the correct gocode `lib-path` by constructing a path using the `goroot`, `goarch`, `goos`, and `gopath` settings entries. For gocode support to work as expected, it's important to set each of those values in the settings.

#### Using alongside GoSublime

Installing GoTools alongside GoSublime isn't tested or supported, so YMMV.
