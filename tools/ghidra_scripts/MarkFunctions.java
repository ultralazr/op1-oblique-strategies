// Disassemble and create functions at the given addresses (script args, hex).
// Usage (headless): -preScript MarkFunctions.java 0x01a42344 0x01a28da0 ...
//@category OP1
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class MarkFunctions extends GhidraScript {
	@Override
	protected void run() throws Exception {
		for (String a : getScriptArgs()) {
			Address addr = toAddr(Long.decode(a.trim()));
			if (getInstructionAt(addr) == null) {
				DisassembleCommand cmd = new DisassembleCommand(addr, null, true);
				cmd.applyTo(currentProgram, monitor);
			}
			Function f = getFunctionAt(addr);
			if (f == null) {
				f = createFunction(addr, null);
			}
			println("MarkFunctions: " + addr + " -> " + (f == null ? "FAILED to create function" : f.getName()));
		}
	}
}
