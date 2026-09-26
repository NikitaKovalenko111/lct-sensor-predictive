package incidents

import "testing"

func TestValidDecision(t *testing.T) {
	valid := []string{
		DecisionConfirmed,
		DecisionFalseAlarm,
		DecisionMonitor,
		DecisionDispatchCrew,
	}
	for _, decision := range valid {
		if !ValidDecision(decision) {
			t.Fatalf("expected %q to be valid", decision)
		}
	}
	if ValidDecision("ignored") {
		t.Fatal("unexpected valid decision")
	}
}
