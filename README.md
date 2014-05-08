# sublime-godef

This Sublime Text 3 plugin adds a `godef` command which uses [godef](http://godoc.org/code.google.com/p/rog-go/exp/cmd/godef)
to find the definition under the cursor.

## Installation

The plugin assumes `godef` is present at `$GOPATH/bin/godef`. 

### Manual

OSX:

    git clone https://github.com/ironcladlou/sublime-godef.git ~/Library/Application\ Support/Sublime\ Text\ 3/Packages/sublime-godef

Linux:

TODO

### Package Control

TODO

## Configuring `GOPATH`

The plugin will determine `GOPATH` from either:

1. The `gopath` value from `sublime-godef.sublime-settings`
2. The `GOPATH` environment variable
