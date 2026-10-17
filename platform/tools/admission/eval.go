package main

// eval mode: evaluates policies against sample admission requests (dynamic JSON objects).
import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/google/cel-go/cel"
)

type nv struct{ Name, Expr string }
type policy struct {
	Name        string
	Variables   []nv
	Validations []string
	Conditions  []string
}
type tcase struct {
	Name    string
	Input   map[string]any
	Expect  map[string]string // policy -> allow|deny|skip
}
type suite struct {
	Policies []policy
	Cases    []tcase
}

func runEval(env *cel.Env, path string) int {
	var s suite
	b, _ := os.ReadFile(path)
	if err := json.Unmarshal(b, &s); err != nil { panic(err) }
	pols := map[string]policy{}
	for _, p := range s.Policies { pols[p.Name] = p }
	prog := func(e string) cel.Program {
		ast, iss := env.Compile(e)
		if iss != nil && iss.Err() != nil { panic(fmt.Sprintf("%s: %v", e, iss.Err())) }
		p, err := env.Program(ast)
		if err != nil { panic(err) }
		return p
	}
	bad := 0
	for _, c := range s.Cases {
		for pn, want := range c.Expect {
			p := pols[pn]
			act := map[string]any{}
			for k, v := range c.Input { act[k] = v }
			vars := map[string]any{}
			act["variables"] = vars
			for _, v := range p.Variables {
				out, _, err := prog(v.Expr).Eval(act)
				if err == nil { vars[v.Name] = out }
			}
			got := "allow"
			why := ""
			for _, m := range p.Conditions {
				out, _, err := prog(m).Eval(act)
				if err != nil || out.Value() != true { got = "skip" }
			}
			if got != "skip" {
				for _, v := range p.Validations {
					out, _, err := prog(v).Eval(act)
					if err != nil { got = "deny"; why = "error: " + err.Error() + " in " + v; break }
					if out.Value() != true { got = "deny"; why = v; break }
				}
			}
			status := "ok  "
			if got != want { status = "BAD "; bad++ }
			fmt.Printf("%s %-34s %-32s want=%-5s got=%-5s %s\n", status, c.Name, pn, want, got, trunc(why))
		}
	}
	fmt.Printf("eval: %d mismatches\n", bad)
	return bad
}

func trunc(s string) string { if len(s) > 110 { return s[:110] + "..." }; return s }
