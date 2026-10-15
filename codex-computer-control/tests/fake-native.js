import readline from 'node:readline';
for await (const line of readline.createInterface({input:process.stdin})){
  const request=JSON.parse(line);if(request.op==='hang')continue;
  if(request.op==='exit')process.exit(2);
  process.stdout.write(JSON.stringify({id:request.id,ok:true,result:{echo:request.op}})+'\n');
}
