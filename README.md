# GoTools

GoTools is a a [Sublime Text 3](http://www.sublimetext.com) plugin inspired by [vim-go](https://github.com/fatih/vim-go). Rather than attempting to reinvent various supporting IDE components, it provides integration with existing community-supported tools for the [Go programming language](http://www.golang.org).

## Features

* Jump to symbol/declaration with [godef](http://godoc.org/code.google.com/p/rog-go/exp/cmd/godef).
* Format on save with [gofmt](http://godoc.org/code.google.com/p/go.tools/cmd/gofmt).
* Syntax errors in an output panel with navigation support.
* Autocompletion support using [gocode](https://github.com/nsf/gocode).
* Improved syntax highlighting using the `tmLanguage` support from [GoSublime](https://github.com/DisposaBoy/GoSublime).

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

## Settings

Access the default and user specified settings via the `Package Settings -> GoTools` menu in Sublime Text. The `gopath` and `go_bin_path` settings are required. Here's an example user settings file:

```json
{
  "go_bin_path": "/home/ironcladlou/projects/go/bin",
  "gopath": "/home/ironcladlou/projects/go",
  "gofmt_enabled": true,
  "gofmt_cmd": "gofmt",
  "gocode_enabled": true
}
```

### Setting GOPATH for projects 

The `GOPATH` can be further customized at the project scope by adding a `GoTools` settings entry to a project's `.sublime-project` file. For example:

```json
{
  "folders": [],
  "settings": {
    "GoTools": {
      "gopath": "/home/ironcladlou/projects/go/src/github.com/some/project/vendor:${gopath}"
    }
  }
}
```

Any occurence of `${gopath}` in the `gopath` setting will be automatically replaced with the `gopath` value from the `GoTools.sublime-settings` file.

This allows for vendored `GOPATH` support to any depth.

### Commands

GoTools provides a `godef` Sublime Text command which can be bound to keys or called by other plugins.

Here's an example key binding:

    { "keys" : ["ctrl+'", "g"], "command": "godef" }

### Syntax Support

To use the syntax support, select `Go (GoTools)` from the `View -> Syntax` menu.
