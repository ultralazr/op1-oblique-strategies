// Create functions at every Blackfin LINK (0xE800) prologue in the stock code range.
//@category OP1
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;

public class MarkLinkFunctions extends GhidraScript {
	@Override
	protected void run() throws Exception {
		long lo = 0x018ab7ccL, hi = 0x01aa7078L;
		Memory mem = currentProgram.getMemory();
		int n = 0, made = 0;
		for (long a = lo & ~1L; a < hi; a += 2) {
			Address addr = toAddr(a);
			int b0 = mem.getByte(addr) & 0xff, b1 = mem.getByte(addr.add(1)) & 0xff;
			if (b0 != 0x00 || b1 != 0xe8) continue;
			n++;
			if (getFunctionAt(addr) != null) continue;
			if (getInstructionAt(addr) == null) {
				new DisassembleCommand(addr, null, true).applyTo(currentProgram, monitor);
			}
			if (createFunction(addr, null) != null) made++;
			if (n % 500 == 0) println("MarkLinkFunctions: " + n + " LINKs, " + made + " created");
		}
		println("MarkLinkFunctions: done " + n + " LINKs, " + made + " created");
	}
}
