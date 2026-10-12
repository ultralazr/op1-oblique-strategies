// Print caller tree of given addresses. Args: <depth> <addr>...
//@category OP1
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import java.util.*;

public class CallersOf extends GhidraScript {
	Set<Function> seen = new HashSet<>();
	void walk(Function f, int depth, int max, String ind) {
		if (depth > max) return;
		Set<Function> callers = new TreeSet<>(Comparator.comparing(Function::getEntryPoint));
		int n = 0;
		for (Reference r : getReferencesTo(f.getEntryPoint())) {
			Function c = getFunctionContaining(r.getFromAddress());
			if (c != null) callers.add(c); else n++;
		}
		println(ind + f.getEntryPoint() + " callers=" + callers.size() + (n > 0 ? " (+" + n + " non-func refs)" : ""));
		if (!seen.add(f)) return;
		if (callers.size() > 25) { println(ind + "  ... too many"); return; }
		for (Function c : callers) walk(c, depth + 1, max, ind + "  ");
	}
	@Override
	protected void run() throws Exception {
		String[] a = getScriptArgs();
		int depth = Integer.parseInt(a[0]);
		for (int i = 1; i < a.length; i++) {
			Function f = getFunctionContaining(toAddr(Long.decode(a[i])));
			if (f == null) { println("no function at " + a[i]); continue; }
			walk(f, 0, depth, "");
		}
	}
}
