package lib

import (
  "testing"
  "time"
)

func TestFooSucceeds(t *testing.T) {
  t.Logf("This one passes: %v", &Foo{})
  time.Sleep(time.Second * 3)
  t.Log("This one passes again")
  time.Sleep(time.Millisecond * 250)
  t.Log("And again")
}

func TestFooFails(t *testing.T) {
  t.Fatal("This one fails")
}
