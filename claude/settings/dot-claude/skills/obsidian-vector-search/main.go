package main

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"

	_ "modernc.org/sqlite"
)

const (
	defaultTopN     = 5
	chunkTokens     = 500
	chunkOverlap    = 100
	embeddingModel  = "perplexity/pplx-embed-v1-4b"
	openrouterURL   = "https://openrouter.ai/api/v1/embeddings"
)

// ---------- DB ----------

func openDB(path string) (*sql.DB, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}
	_, err = db.Exec(`CREATE TABLE IF NOT EXISTS chunks (
		id          INTEGER PRIMARY KEY AUTOINCREMENT,
		file_path   TEXT NOT NULL,
		title       TEXT,
		heading     TEXT,
		content     TEXT NOT NULL,
		embedding   BLOB NOT NULL,
		modified_at INTEGER NOT NULL
	)`)
	if err != nil {
		return nil, err
	}
	_, err = db.Exec(`CREATE INDEX IF NOT EXISTS idx_file_path ON chunks(file_path)`)
	return db, err
}

// ---------- Chunking ----------

var headingRe = regexp.MustCompile(`(?m)^#{1,6} .+$`)

func chunkFile(content, title string) []struct{ heading, text string } {
	// Split on headings
	locs := headingRe.FindAllStringIndex(content, -1)
	var sections []struct{ heading, body string }

	if len(locs) == 0 {
		sections = append(sections, struct{ heading, body string }{"", content})
	} else {
		if locs[0][0] > 0 {
			sections = append(sections, struct{ heading, body string }{"", content[:locs[0][0]]})
		}
		for i, loc := range locs {
			heading := content[loc[0]:loc[1]]
			var body string
			if i+1 < len(locs) {
				body = content[loc[1]:locs[i+1][0]]
			} else {
				body = content[loc[1]:]
			}
			sections = append(sections, struct{ heading, body string }{heading, body})
		}
	}

	// Sliding window within sections that are too long
	var chunks []struct{ heading, text string }
	for _, sec := range sections {
		combined := strings.TrimSpace(sec.heading + "\n" + sec.body)
		words := strings.Fields(combined)
		if len(words) <= chunkTokens {
			if len(strings.TrimSpace(combined)) > 0 {
				chunks = append(chunks, struct{ heading, text string }{sec.heading, combined})
			}
			continue
		}
		for start := 0; start < len(words); start += chunkTokens - chunkOverlap {
			end := start + chunkTokens
			if end > len(words) {
				end = len(words)
			}
			chunks = append(chunks, struct{ heading, text string }{sec.heading, strings.Join(words[start:end], " ")})
			if end == len(words) {
				break
			}
		}
	}
	return chunks
}

// ---------- Embeddings ----------

type embedRequest struct {
	Model string   `json:"model"`
	Input []string `json:"input"`
}

type embedResponse struct {
	Data []struct {
		Embedding []float32 `json:"embedding"`
	} `json:"data"`
	Error *struct {
		Message string `json:"message"`
	} `json:"error"`
}

func getEmbeddings(apiKey string, texts []string) ([][]float32, error) {
	body, _ := json.Marshal(embedRequest{Model: embeddingModel, Input: texts})
	req, _ := http.NewRequest("POST", openrouterURL, bytes.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+apiKey)
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)

	var result embedResponse
	if err := json.Unmarshal(data, &result); err != nil {
		return nil, fmt.Errorf("parse error: %w — body: %s", err, data)
	}
	if result.Error != nil {
		return nil, fmt.Errorf("API error: %s", result.Error.Message)
	}
	out := make([][]float32, len(result.Data))
	for i, d := range result.Data {
		out[i] = d.Embedding
	}
	return out, nil
}

func embeddingToBlob(e []float32) []byte {
	buf := make([]byte, len(e)*4)
	for i, v := range e {
		bits := math.Float32bits(v)
		buf[i*4] = byte(bits)
		buf[i*4+1] = byte(bits >> 8)
		buf[i*4+2] = byte(bits >> 16)
		buf[i*4+3] = byte(bits >> 24)
	}
	return buf
}

func blobToEmbedding(b []byte) []float32 {
	e := make([]float32, len(b)/4)
	for i := range e {
		bits := uint32(b[i*4]) | uint32(b[i*4+1])<<8 | uint32(b[i*4+2])<<16 | uint32(b[i*4+3])<<24
		e[i] = math.Float32frombits(bits)
	}
	return e
}

// ---------- Cosine similarity ----------

func cosine(a, b []float32) float64 {
	var dot, normA, normB float64
	for i := range a {
		dot += float64(a[i]) * float64(b[i])
		normA += float64(a[i]) * float64(a[i])
		normB += float64(b[i]) * float64(b[i])
	}
	if normA == 0 || normB == 0 {
		return 0
	}
	return dot / (math.Sqrt(normA) * math.Sqrt(normB))
}

// ---------- Indexing ----------

func cmdIndex(vaultPath, dbPath, apiKey string) error {
	db, err := openDB(dbPath)
	if err != nil {
		return fmt.Errorf("open db: %w", err)
	}
	defer db.Close()

	// Load existing file mtimes
	rows, err := db.Query(`SELECT DISTINCT file_path, modified_at FROM chunks`)
	if err != nil {
		return err
	}
	indexed := map[string]int64{}
	for rows.Next() {
		var path string
		var mtime int64
		rows.Scan(&path, &mtime)
		indexed[path] = mtime
	}
	rows.Close()

	skipDirs := map[string]bool{
		".obsidian": true, ".trash": true, ".claude": true,
		".git": true, "node_modules": true,
	}

	type fileJob struct {
		absPath, relPath, title string
		mtime                   int64
	}
	var toProcess []fileJob

	err = filepath.WalkDir(vaultPath, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			if strings.HasPrefix(d.Name(), ".") || skipDirs[d.Name()] {
				return filepath.SkipDir
			}
			return nil
		}
		if !strings.HasSuffix(d.Name(), ".md") {
			return nil
		}
		info, err := d.Info()
		if err != nil {
			return nil
		}
		mtime := info.ModTime().UnixMilli()
		relPath, _ := filepath.Rel(vaultPath, path)
		title := strings.TrimSuffix(d.Name(), ".md")

		if prev, ok := indexed[relPath]; ok && prev == mtime {
			return nil // unchanged
		}
		toProcess = append(toProcess, fileJob{path, relPath, title, mtime})
		return nil
	})
	if err != nil {
		return err
	}

	fmt.Fprintf(os.Stderr, "Indexing %d changed/new files...\n", len(toProcess))

	type chunkJob struct {
		filePath, title, heading, content string
		mtime                             int64
	}

	// buildChunks reads and chunks a single file.
	buildChunks := func(f fileJob) []chunkJob {
		raw, err := os.ReadFile(f.absPath)
		if err != nil {
			return nil
		}
		content := string(raw)
		if !utf8.ValidString(content) {
			return nil
		}
		if strings.HasPrefix(content, "---\n") {
			if idx := strings.Index(content[4:], "\n---"); idx >= 0 {
				content = strings.TrimSpace(content[4+idx+4:])
			}
		}
		var out []chunkJob
		for _, c := range chunkFile(content, f.title) {
			out = append(out, chunkJob{f.relPath, f.title, c.heading, c.text, f.mtime})
		}
		return out
	}

	// indexFiles embeds and stores chunks for a slice of files.
	// Returns an error only if ALL files in the slice fail at batch size 1.
	var indexFiles func(files []fileJob) error
	indexFiles = func(files []fileJob) error {
		if len(files) == 0 {
			return nil
		}

		var chunks []chunkJob
		for _, f := range files {
			chunks = append(chunks, buildChunks(f)...)
		}
		if len(chunks) == 0 {
			return nil
		}

		texts := make([]string, len(chunks))
		for i, c := range chunks {
			texts[i] = c.title + "\n" + c.heading + "\n" + c.content
		}

		embeddings, err := getEmbeddings(apiKey, texts)
		if err != nil {
			if len(files) == 1 {
				fmt.Fprintf(os.Stderr, "  skipping %s: %v\n", files[0].relPath, err)
				return nil
			}
			// Halve and retry
			mid := len(files) / 2
			if e := indexFiles(files[:mid]); e != nil {
				return e
			}
			return indexFiles(files[mid:])
		}

		tx, _ := db.Begin()
		for _, f := range files {
			tx.Exec(`DELETE FROM chunks WHERE file_path = ?`, f.relPath)
		}
		for i, c := range chunks {
			tx.Exec(`INSERT INTO chunks (file_path, title, heading, content, embedding, modified_at)
				VALUES (?, ?, ?, ?, ?, ?)`,
				c.filePath, c.title, c.heading, c.content,
				embeddingToBlob(embeddings[i]), c.mtime)
		}
		tx.Commit()
		return nil
	}

	const batchSize = 20
	done := 0
	for batchStart := 0; batchStart < len(toProcess); batchStart += batchSize {
		end := batchStart + batchSize
		if end > len(toProcess) {
			end = len(toProcess)
		}
		if err := indexFiles(toProcess[batchStart:end]); err != nil {
			return err
		}
		done = end
		fmt.Fprintf(os.Stderr, "  indexed %d/%d files\n", done, len(toProcess))
	}

	fmt.Fprintln(os.Stderr, "Done.")
	return nil
}

// ---------- Search ----------

type SearchResult struct {
	Path    string  `json:"path"`
	Title   string  `json:"title"`
	Heading string  `json:"heading"`
	Score   float64 `json:"score"`
	Snippet string  `json:"snippet"`
}

func cmdSearch(query, dbPath, apiKey string, topN int) error {
	db, err := openDB(dbPath)
	if err != nil {
		return fmt.Errorf("open db: %w", err)
	}
	defer db.Close()

	embeddings, err := getEmbeddings(apiKey, []string{query})
	if err != nil {
		return fmt.Errorf("embedding query: %w", err)
	}
	queryEmbed := embeddings[0]

	rows, err := db.Query(`SELECT file_path, title, heading, content, embedding FROM chunks`)
	if err != nil {
		return err
	}
	defer rows.Close()

	type scored struct {
		SearchResult
		score float64
	}
	var results []scored

	for rows.Next() {
		var path, title, heading, content string
		var blob []byte
		rows.Scan(&path, &title, &heading, &content, &blob)
		emb := blobToEmbedding(blob)
		score := cosine(queryEmbed, emb)
		results = append(results, scored{
			SearchResult: SearchResult{
				Path:    path,
				Title:   title,
				Heading: heading,
				Score:   score,
				Snippet: snippet(content, 200),
			},
			score: score,
		})
	}

	// Sort descending
	for i := 0; i < len(results)-1; i++ {
		for j := i + 1; j < len(results); j++ {
			if results[j].score > results[i].score {
				results[i], results[j] = results[j], results[i]
			}
		}
	}

	if topN > len(results) {
		topN = len(results)
	}
	out := make([]SearchResult, topN)
	for i := range out {
		out[i] = results[i].SearchResult
	}

	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	return enc.Encode(out)
}

func snippet(text string, maxLen int) string {
	text = strings.TrimSpace(text)
	if len(text) <= maxLen {
		return text
	}
	return text[:maxLen] + "..."
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// ---------- Main ----------

func apiKey() string {
	if k := os.Getenv("OPENROUTER_API_KEY"); k != "" {
		return k
	}
	// Try .env next to binary
	exe, _ := os.Executable()
	envPath := filepath.Join(filepath.Dir(exe), ".env")
	data, err := os.ReadFile(envPath)
	if err != nil {
		return ""
	}
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "OPENROUTER_API_KEY=") {
			return strings.TrimPrefix(line, "OPENROUTER_API_KEY=")
		}
	}
	return ""
}

func usage() {
	fmt.Fprintln(os.Stderr, `Usage:
  vector index --vault /path/to/vault [--db ./vector.db]
  vector search "query string" [--top 5] [--db ./vector.db]

Environment:
  OPENROUTER_API_KEY  required (or set in .env next to binary)`)
	os.Exit(1)
}

func main() {
	if len(os.Args) < 2 {
		usage()
	}

	key := apiKey()
	if key == "" {
		fmt.Fprintln(os.Stderr, "Error: OPENROUTER_API_KEY not set")
		os.Exit(1)
	}

	// Default db path: next to the binary
	exe, _ := os.Executable()
	defaultDB := filepath.Join(filepath.Dir(exe), "vector.db")

	switch os.Args[1] {
	case "index":
		var vault, db string
		db = defaultDB
		args := os.Args[2:]
		for i := 0; i < len(args); i++ {
			switch args[i] {
			case "--vault":
				i++
				vault = args[i]
			case "--db":
				i++
				db = args[i]
			}
		}
		if vault == "" {
			fmt.Fprintln(os.Stderr, "Error: --vault required")
			os.Exit(1)
		}
		if err := cmdIndex(vault, db, key); err != nil {
			fmt.Fprintln(os.Stderr, "Error:", err)
			os.Exit(1)
		}

	case "search":
		if len(os.Args) < 3 {
			usage()
		}
		query := os.Args[2]
		topN := defaultTopN
		db := defaultDB
		args := os.Args[3:]
		for i := 0; i < len(args); i++ {
			switch args[i] {
			case "--top":
				i++
				fmt.Sscan(args[i], &topN)
			case "--db":
				i++
				db = args[i]
			}
		}
		if err := cmdSearch(query, db, key, topN); err != nil {
			fmt.Fprintln(os.Stderr, "Error:", err)
			os.Exit(1)
		}

	default:
		usage()
	}
}
