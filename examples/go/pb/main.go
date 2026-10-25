package main

import (
	"time"

	"github.com/cheggaaa/pb/v3"
)

func main() {
	bar := pb.StartNew(60)
	for i := 0; i < 60; i++ {
		bar.Increment()
		time.Sleep(80 * time.Millisecond)
	}
	bar.Finish()
}
