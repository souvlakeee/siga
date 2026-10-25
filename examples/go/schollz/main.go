package main

import (
	"time"

	"github.com/schollz/progressbar/v3"
)

func main() {
	bar := progressbar.Default(60, "converting")
	for i := 0; i < 60; i++ {
		bar.Add(1)
		time.Sleep(80 * time.Millisecond)
	}
}
