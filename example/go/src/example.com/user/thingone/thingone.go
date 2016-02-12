package main

import (
	"fmt"

	"example.com/user/thingone/lib"
)

func main() {
	s := lib.Splatchet{
		Wizzle: "snark",
	}
	fmt.Println("it's a %v", s)
}
