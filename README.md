# GoTools

GoTools is a a Sublime Text 3 plugin inspired by [vim-go](https://github.com/fatih/vim-go). It provides integration with various community-supported tools for the [Go programming language](http://www.golang.org).


## Commands

The plugin adds some commands to Sublime Text suitable for binding to keys or calling from other plugins.

### godef

The `godef` command uses [godef](http://godoc.org/code.google.com/p/rog-go/exp/cmd/godef) to jump to the definition under the cursor.

### goimports

The `goimports` command uses [goimports](http://godoc.org/code.google.com/p/go.tools/cmd/goimports) to format source and manage imports during file save.

## Installation

The plugin assumes all supporting binaries are located in `go_bin_path` defined in the settings. Use `go get` to install them, e.g.:

    go get -v code.google.com/p/rog-go/exp/cmd/godef
    go get -v code.google.com/p/go.tools/cmd/goimports

Install the plugin manually:

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
  "goimports_on_save": true
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

### Key Bindings

Here's an example key binding:

    { "keys" : ["ctrl+'", "g"], "command": "godef" }
