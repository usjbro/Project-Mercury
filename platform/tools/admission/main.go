// Offline CEL compile check for ValidatingAdmissionPolicy expressions using the Kubernetes v0.33 base CEL
// environment (k8s libraries + ext strings etc.). object/oldObject/params/namespaceObject/request are DynType,
// so this checks syntax, function/overload names and macro use, NOT field typing against OpenAPI schemas.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/google/cel-go/cel"
	"k8s.io/apimachinery/pkg/util/version"
	"k8s.io/apiserver/pkg/cel/environment"
)

type item struct{ Policy, Kind, Name, Expr string }

func main() {
	base := environment.MustBaseEnvSet(version.MajorMinor(1, 33), true)
	es, err := base.Extend(environment.VersionedOptions{
		IntroducedVersion: version.MajorMinor(1, 0),
		EnvOptions: []cel.EnvOption{
			cel.Variable("object", cel.DynType), cel.Variable("oldObject", cel.DynType),
			cel.Variable("params", cel.DynType), cel.Variable("namespaceObject", cel.DynType),
			cel.Variable("request", cel.DynType), cel.Variable("authorizer", cel.DynType),
			cel.Variable("variables", cel.MapType(cel.StringType, cel.DynType)),
		},
	})
	if err != nil { panic(err) }
	env, err := es.Env(environment.StoredExpressions)
	if err != nil { panic(err) }
	if os.Args[1] == "eval" { os.Exit(runEval(env, os.Args[2])) }
	var items []item
	b, _ := os.ReadFile(os.Args[1])
	if err := json.Unmarshal(b, &items); err != nil { panic(err) }
	fail := 0
	for _, it := range items {
		ast, iss := env.Compile(it.Expr)
		if iss != nil && iss.Err() != nil {
			fail++
			fmt.Printf("FAIL %s %s %s: %v\n", it.Policy, it.Kind, it.Name, iss.Err())
			continue
		}
		if _, err := env.Program(ast); err != nil {
			fail++
			fmt.Printf("FAIL(program) %s %s %s: %v\n", it.Policy, it.Kind, it.Name, err)
		}
	}
	fmt.Printf("compiled %d expressions, %d failures\n", len(items), fail)
	if fail > 0 { os.Exit(1) }
}
