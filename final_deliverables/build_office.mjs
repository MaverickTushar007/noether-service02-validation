import fs from 'node:fs/promises';
import {Workbook,SpreadsheetFile,Presentation,PresentationFile} from '@oai/artifact-tool';
const dir=process.argv[3]+'/';
const root=process.argv[2];
const inputs=JSON.parse(await fs.readFile(dir+'workbook-input.json','utf8'));
function grid(w,name,rows,widths){
 const s=w.worksheets.add(name);
 const n=rows.length;
 const end=String.fromCharCode(64+rows[0].length);
 s.getRange('A1:'+end+n).values=rows;
 const h=s.getRange('A1:'+end+'1'); h.format.fill='#193443';h.format.font.color='#FFFFFF';h.format.font.bold=true;
 h.format.rowHeight=28;
 const body=s.getRange('A2:'+end+n);body.format.wrapText=true;body.format.rowHeight=65;
 widths.forEach((value,i)=>{const c=String.fromCharCode(65+i);s.getRange(c+':'+c).format.columnWidth=value;});
 for(let i=2;i<=n;i+=2)s.getRange('A'+i+':'+end+i).format.fill='#EEF5F5';
 s.freezePanes.freezeRows(1);
 return s;
}
const findings=inputs['findings-register.csv'];
const traces=inputs['claim-traceability.csv'];
const widths=[13,32,20,13,19,44,48,47,22,24,25,15,17,42,65];
const fw=Workbook.create();
grid(fw,'Findings',findings,widths);
await (await SpreadsheetFile.exportXlsx(fw)).save(dir+'findings-register.xlsx');
const mw=Workbook.create();
const overview=grid(mw,'Validation summary',[
 ['Decision','Result','Basis'],
 ['PASS',null,'Consolidated material findings'],
 ['FAIL',null,'Consolidated material findings'],
 ['INCONCLUSIVE',null,'Consolidated material findings'],
 ['Approval','PENDING','Internal simulation']
],[23,22,43]);
grid(mw,'Findings',findings,widths);
grid(mw,'Claim traceability',traces,[13,44,16,46,76,64,70]);
overview.getRange('B2:B4').formulas=['PASS','FAIL','INCONCLUSIVE'].map((_,i)=>[`=COUNTIF(Findings!C2:C14,A${i+2})`]);
mw.recalculate();
const counts=overview.getRange('B2:B4').values.flat();
if(JSON.stringify(counts)!==JSON.stringify([5,0,8])) throw Error('Bad counts '+JSON.stringify(counts));
await (await SpreadsheetFile.exportXlsx(mw)).save(dir+'validation-matrix.xlsx');
console.log('Workbook formula results',counts);
const deck=Presentation.create({slideSize:{width:1280,height:720}});
function text(slide,value,x,y,w,h,size,color='#203643',bold=false){
 let a=slide.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 a.text=value; a.text.style={fontSize:size,color,bold,typeface:'Arial'};return a;
}
function page(title,source){
 const slide=deck.slides.add();slide.background.fill='#F8FAF9';
 text(slide,'NOETHER MERIDIAN / SERVICE 02 / UNIT 1',60,28,1150,28,17,'#17676B',true);
 text(slide,title,60,79,1150,90,47,'#173343',true);
 text(slide,source+'   |   INTERNAL DEMONSTRATION   |   SIGN-OFF PENDING',60,669,1160,25,15,'#496573');
 return slide;
}
function block(s,heading,copy,y){
 text(s,heading,64,y,330,55,29,'#17676B',true);
 text(s,copy,405,y,800,115,28);
}
async function picture(s,file,x,y,w,h){
 const b=await fs.readFile(root+'/'+file);
 s.images.add({blob:b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength),contentType:'image/png',fit:'contain',alt:file,position:{left:x,top:y,width:w,height:h}});
}
let s=page('Independent strategy validation','E01–E07');
text(s,'Hypothetical SPY SMA 21/50',64,225,1120,74,55,'#17676B',true);
text(s,'Internal review for Roosevelt PETNGA',64,330,1130,60,36);
text(s,'Calculations reproduced. Predictive reliability and incremental value remain inconclusive.',64,435,1050,130,32);
s=page('The arithmetic reconciled','E01–E03 • T02–T08');
block(s,'Frozen data','3,020 SPY sessions from 2011 through 2022.',205);
block(s,'Independent review','57 field checks passed. Signals use completed closes and fill at the following open.',338);
block(s,'Scope','Hypothetical 5 bp per-fill cost. No real client model or approval.',477);
s=page('Development uncertainty remains wide','E04 • T09–T11');
await picture(s,'evidence/phase4-review/bootstrap_intervals.png',52,179,770,365);
text(s,'5.34% CAGR',867,235,340,58,38,'#17676B',true);
text(s,'All three mean-return intervals include zero. The lookback and fee tests were exploratory.',864,310,341,208,25);
s=page('The SMA lagged both SPY benchmarks','E05 • T12–T14');
await picture(s,'evidence/phase5-review/equity.png',53,170,1150,360);
text(s,'Holdout return: SMA 23.14%  /  Fixed mix 45.06%  /  Buy and hold 66.20%',60,560,1160,54,27,'#17676B',true);
s=page('The primary holdout result is inconclusive','E05 • T13–T15');
block(s,'−21.92 points','Observed cumulative gap versus the fixed SPY/cash mix.',195);
block(s,'−4.25 points','Paired annualized arithmetic difference.',326);
block(s,'−13.31 to +7.01','95% paired interval. The data do not resolve the direction of the incremental mean.',458);
s=page('Exposure changed the risk profile','E05–E06 • T15–T17');
await picture(s,'evidence/phase5-review/drawdown.png',53,170,1150,350);
text(s,'Holdout maximum drawdown: SMA 26.13%  /  Fixed mix 23.16%',60,558,1160,54,28,'#17676B',true);
s=page('Decisions for internal review','E05–E07 • T16–T19');
block(s,'Cash convention','Decide whether to authorize a matched-cash sensitivity. The original SMA earns zero idle interest.',187);
block(s,'Execution evidence','Obtain payment-date and executable cost evidence before a deployment-oriented review.',332);
block(s,'Governance','Assign a human reviewer, agree on an economic hurdle, and retain pending sign-off.',475);
await fs.mkdir('/tmp/nm-final/slide-preview',{recursive:true});
for(let i=0;i<deck.slides.items.length;i++){
 const blob=await deck.export({slide:deck.slides.items[i],format:'png',scale:1});
 await fs.writeFile('/tmp/nm-final/slide-preview/slide-'+(i+1)+'.png',new Uint8Array(await blob.arrayBuffer()));
}
await (await PresentationFile.exportPptx(deck)).save(dir+'roosevelt-briefing.pptx');
