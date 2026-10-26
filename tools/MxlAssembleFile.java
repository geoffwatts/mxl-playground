//@category Mxl
// Assemble an explicitly addressed instruction list offline. Never device I/O.
import ghidra.app.script.GhidraScript;
import ghidra.app.plugin.assembler.*;
import java.nio.file.*;
import java.io.*;
public class MxlAssembleFile extends GhidraScript {
 public void run()throws Exception{
  String[] args=getScriptArgs();Assembler asm=Assemblers.getAssembler(currentProgram);
  try(PrintWriter out=new PrintWriter(new FileWriter(args[1]))){
   for(String line:Files.readAllLines(Path.of(args[0]))){
    if(line.isBlank()||line.startsWith("#"))continue;
    String[] parts=line.split("\\|",2);long at=Long.decode(parts[0]);
    try{
     byte[] bytes=asm.assembleLine(toAddr(at),parts[1]);
     out.printf("%08x|%s|",at,parts[1]);for(byte b:bytes)out.printf("%02x",b&255);out.println();
    }catch(Exception e){out.printf("ERROR|%s|%s%n",parts[1],e.getClass().getSimpleName());}
   }
  }
 }
}
