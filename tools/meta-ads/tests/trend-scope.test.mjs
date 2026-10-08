import test from 'node:test';
import assert from 'node:assert/strict';
import {scopeRows,observationKey,categorySources,fixedSettings,notesForCategory} from '../trend-scope.mjs';

const health={category:'50000023',keyword:'유산균',previousDate:'2026-09-29',currentDate:'2026-10-06',previousRank:60,currentRank:20};
const diet={...health,category:'50000024',previousRank:30,currentRank:5};

test('public display filtering preserves separate same-keyword category observations',()=>{
  const rows=[health,diet,{...health,category:'50001092'},{keyword:'분야 미확인'}];
  assert.deepEqual(scopeRows(rows),[health,diet]);
  assert.deepEqual(scopeRows(rows,'50000023'),[health]);
  assert.deepEqual(scopeRows(rows,'50000024'),[diet]);
  assert.deepEqual(scopeRows(rows,'unknown'),[]);
  assert.notEqual(observationKey(health),observationKey(diet));
  assert.notEqual(observationKey(health),observationKey({...health,previousDate:'2026-09-28'}));
});

test('display filters never change the fixed two-category collection settings',()=>{
  const settings=fixedSettings('10','20');
  assert.deepEqual(settings,{categories:['50000023','50000024'],category:'50000023',minimumRise:10,newTop:20});
  scopeRows([health,diet],'50000024');
  assert.deepEqual(fixedSettings(10,20),settings);
  settings.categories.pop();
  assert.equal(fixedSettings(10,20).categories.length,2);
});

test('a current healthy source cannot hide a stale or failed second category',()=>{
  const value={sourceDate:'2026-10-07',sourceSummaries:[
    {category:'50000023',sourceDate:'2026-10-07',previousSourceDate:'2026-09-30',lastChecked:'2026-10-08T11:00:00+09:00'},
    {category:'50000024',sourceDate:'2026-10-05',previousSourceDate:'2026-09-28',error:'조회 지연'}]};
  const sources=categorySources(value);
  assert.equal(sources[0].sourceDate,'2026-10-07');
  assert.equal(sources[1].sourceDate,'2026-10-05');
  assert.equal(sources[1].error,'조회 지연');
});

test('legacy single-category dates are never claimed as dates for both categories',()=>{
  const sources=categorySources({settings:{category:'50000023'},sourceDate:'2026-10-06',previousSourceDate:'2026-09-29'});
  assert.equal(sources[0].sourceDate,'2026-10-06');
  assert.equal(sources[1].sourceDate,null);
  assert.equal(sources[1].lastChecked,null);
});

test('missing source summaries remain pending even when a generic top-level date exists',()=>{
  assert.deepEqual(categorySources({sourceDate:'2026-10-07'}).map(source=>source.sourceDate),[null,null]);
  assert.deepEqual(categorySources({sourceSummaries:[{category:'50000024'}]}).map(source=>source.sourceDate),[null,null]);
});

test('notes with an unverified or different category do not become cross-category evidence',()=>{
  const notes=[{category:'50000023',keyword:'유산균'},
    {comparison:{category:'50000024'},keyword:'유산균'}, {keyword:'유산균'}];
  assert.deepEqual(notesForCategory(notes,'50000023'),[notes[0]]);
  assert.deepEqual(notesForCategory(notes,'50000024'),[notes[1]]);
});
