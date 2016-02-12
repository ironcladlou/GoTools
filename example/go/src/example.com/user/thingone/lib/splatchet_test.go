package lib

import (
	"testing"
	"time"
)

func TestSplatchet(t *testing.T) {
	t.Log("This one passes")
	time.Sleep(time.Second * 1)
	t.Log("This one passes again")
	time.Sleep(time.Second * 1)`
	t.Log("And again")
}

func TestSplatchetFails(t *testing.T) {
	t.Fatal("This one fails!!")
}
