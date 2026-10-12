// Decompile functions at the given addresses and write <outdir>/<addr>.c
// Script args: <outdir> <addr> [<addr> ...]   (addr hex, e.g. 0x01a42344)
// If no function exists at addr, the code is disassembled and a function is created.
// If addr lies inside an existing function, that function is decompiled.
//@category OP1
import java.io.File;
import java.io.PrintWriter;

import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class DecompileAt extends GhidraScript {
	@Override
	protected void run() throws Exception {
		String[] args = getScriptArgs();
		if (args.length < 2) {
			printerr("usage: DecompileAt.java <outdir> <addr> [<addr>...]");
			return;
		}
		File outDir = new File(args[0]);
		outDir.mkdirs();

		DecompInterface ifc = new DecompInterface();
		DecompileOptions opts = new DecompileOptions();
		ifc.setOptions(opts);
		ifc.toggleCCode(true);
		ifc.toggleSyntaxTree(true);
		ifc.setSimplificationStyle("decompile");
		if (!ifc.openProgram(currentProgram)) {
			printerr("Decompiler failed to open program: " + ifc.getLastMessage());
			return;
		}
		try {
			for (int i = 1; i < args.length; i++) {
				String a = args[i].trim();
				Address addr = toAddr(Long.decode(a));
				Function f = getFunctionAt(addr);
				if (f == null) {
					Function containing = getFunctionContaining(addr);
					if (containing != null) {
						f = containing;
					}
					else {
						if (getInstructionAt(addr) == null) {
							new DisassembleCommand(addr, null, true).applyTo(currentProgram, monitor);
						}
						f = createFunction(addr, null);
					}
				}
				String name = String.format("0x%08x", addr.getOffset());
				File out = new File(outDir, name + ".c");
				if (f == null) {
					printerr("DecompileAt: could not create function at " + addr);
					try (PrintWriter pw = new PrintWriter(out, "UTF-8")) {
						pw.println("/* ERROR: could not create function at " + addr + " */");
					}
					continue;
				}
				DecompileResults res = ifc.decompileFunction(f, 120, monitor);
				try (PrintWriter pw = new PrintWriter(out, "UTF-8")) {
					pw.println("/* function " + f.getName() + " entry " + f.getEntryPoint() +
						" body " + f.getBody().getMinAddress() + "-" + f.getBody().getMaxAddress() +
						" (requested " + addr + ") */");
					if (res != null && res.decompileCompleted() && res.getDecompiledFunction() != null) {
						pw.println(res.getDecompiledFunction().getC());
					}
					else {
						pw.println("/* DECOMPILATION FAILED: " +
							(res == null ? "null result" : res.getErrorMessage()) + " */");
					}
				}
				println("DecompileAt: wrote " + out.getAbsolutePath());
			}
		}
		finally {
			ifc.dispose();
		}
	}
}
