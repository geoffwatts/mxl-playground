//@category Mxl
// Decode every planned instruction in a separate overlay, independently of the assembler.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.pcode.*;
import java.nio.file.*;
import java.io.*;
public class MxlVerifyInstructions extends GhidraScript {
 public void run()throws Exception{
  String[] a=getScriptArgs();long base=Long.decode(a[3]);byte[] b=Files.readAllBytes(Path.of(a[0]));
  MemoryBlock block=currentProgram.getMemory().createInitializedBlock(a[4],toAddr(base),new ByteArrayInputStream(b),b.length,monitor,true);block.setExecute(true);
  AddressSpace space=block.getStart().getAddressSpace();int count=0;
  try(PrintWriter out=new PrintWriter(new FileWriter(a[2]))){
   for(String line:Files.readAllLines(Path.of(a[1]))){
    if(line.isBlank())continue;String[] p=line.split("\\|",3);Address at=space.getAddress(Long.decode(p[0]));disassemble(at);
    Instruction i=getInstructionAt(at);int expected=p[1].length()/2;
    if(i==null||i.getLength()!=expected)throw new Exception("Decode/size mismatch at "+at+" for "+p[2]);
    out.println(at+" "+i+" ; planned "+p[2]);for(PcodeOp op:i.getPcode())out.println("    "+op);count++;
   }
   out.println("VERIFIED "+count+" independently decoded instruction lengths; review semantics before installing.");
  }
 }
}
