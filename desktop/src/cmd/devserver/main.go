package main

import (
	"log"
	"net/http"
	"os"
)

func main() {
	port := os.Getenv("WAILS_VITE_PORT")
	if port == "" {
		port = "9245"
	}

	server := &http.Server{
		Addr:    "localhost:" + port,
		Handler: http.FileServer(http.Dir("assets")),
	}
	log.Printf("serving shell assets on http://%s", server.Addr)
	log.Fatal(server.ListenAndServe())
}
