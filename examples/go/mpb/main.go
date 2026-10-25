package main

import (
	"time"

	"github.com/vbauerster/mpb/v8"
	"github.com/vbauerster/mpb/v8/decor"
)

func main() {
	p := mpb.New()
	bar := p.AddBar(60, mpb.PrependDecorators(decor.Name("syncing")), mpb.AppendDecorators(decor.Percentage()))
	for i := 0; i < 60; i++ {
		bar.Increment()
		time.Sleep(80 * time.Millisecond)
	}
	p.Wait()
}
