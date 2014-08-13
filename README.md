# sublime-go

A Sublime Text 3 plugin inspired by [vim-go](https://github.com/fatih/vim-go). It provides integration with various community-supported tools for the [Go programming language](http://www.golang.org).


## Commands

The plugin adds some commands to Sublime Text.

### godef

The `godef` command uses [godef](http://godoc.org/code.google.com/p/rog-go/exp/cmd/godef) to jump to the definition under the cursor.

### goimports

The `goimports` command uses [goimports](http://godoc.org/code.google.com/p/go.tools/cmd/goimports) to format source and manage imports during file save.

## Installation

The plugin assumes all supporting binaries are present at `go_bin_path` (see the configuration setting).

    go get -v code.google.com/p/rog-go/exp/cmd/godef
    go get code.google.com/p/go.tools/cmd/goimports

OSX:

    # Install the plugin
    git clone git@github.com:ironcladlou/sublime-godef.git ~/Library/Application\ Support/Sublime\ Text\ 3/Packages/sublime-go

    # Create settings file
    # ~/Library/Application\ Support/Sublime\ Text\ 3/Packages/User/sublime-go.sublime-settings

Linux:

    # Install the plugin
    git clone git@github.com:ironcladlou/sublime-godef.git ~/.config/sublime-text-3/Packages/sublime-go

    # Create the settings file
    # ~/.config/sublime-text-3/Packages/User/sublime-go.sublime-settings

## Settings

### Configuration and GOPATH

For Go tool operations, `GOPATH` is resolved with the following order of precedence from least to most preferred:

1. The `GOPATH` environment variable
1. The `gopath` value from `sublime-go.sublime-settings`
1. The `gopath` value from the current project's settings file

Here's an example `sublime-go.sublime-settings`:

```json
{
  "sublime-go": {
    "go_bin_path": "/home/ironcladlou/projects/go/bin",
    "gopath": "/home/ironcladlou/projects/go",
    "debug_enabled": false,
    "goimports_on_save": true
  }
}
```

If `gopath` is unset, it will default to the `GOPATH` environment variable value.

The `GOPATH` can be further customized at the project scope by adding a `sublime-go` settings entry to a `.sublime-project` file. For example:

```json
{
  "settings": {
    "sublime-go": {
      "gopath": "/home/ironcladlou/projects/go/src/github.com/some/project/vendor:${gopath}"
    }
  }
}
```

Any occurance of `${gopath}` in the `gopath` setting will be automatically replaced with the `gopath` value from the `sublime-go.sublime-settings` file.

This allows for vendored `GOPATH` support to any depth.

### Key Bindings

Here's an example key binding:

    { "keys" : ["ctrl+'", "g"], "command": "godef" }
