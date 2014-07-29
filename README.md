# sublime-godef

This Sublime Text 3 [golang](golang.org) plugin adds a `godef` command which
uses [godef](http://godoc.org/code.google.com/p/rog-go/exp/cmd/godef) to find
the definition under the cursor.

## Installation

The plugin assumes `godef` is present at `$GOPATH/bin/godef`:

    go get -v code.google.com/p/rog-go/exp/cmd/gode

OSX:

    # Install the plugin
    git clone git@github.com:ironcladlou/sublime-godef.git ~/Library/Application\ Support/Sublime\ Text\ 3/Packages/sublime-godef

    # Create settings file
    # ~/Library/Application\ Support/Sublime\ Text\ 3/Packages/User/sublime-godef.sublime-settings

Linux:

    # Install the plugin
    git clone git@github.com:ironcladlou/sublime-godef.git ~/.config/sublime-text-3/Packages/sublime-godef

    # Create the settings file
    # ~/.config/sublime-text-3/Packages/User/sublime-godef.sublime-settings

## Settings

### Configuring `GOPATH`

Here's an example `sublime-godef.sublime-settings`:

    {
      "gopath": "/home/ironcladlou/code/go",
      "debug_enabled": false
    }

The plugin will determine `GOPATH` from either:

1. The `gopath` value from `sublime-godef.sublime-settings`
2. The `GOPATH` environment variable


### Key Bindings

Here's an example key binding:

    { "keys" : ["ctrl+'", "g"], "command": "godef" }
