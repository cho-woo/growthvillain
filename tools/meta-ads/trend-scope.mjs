export const TREND_CATEGORIES = Object.freeze(['50000023', '50000024']);
const NAMES = Object.freeze({'50000023':'건강식품', '50000024':'다이어트식품'});
export const categoryName = category => NAMES[String(category)] || '분야 미확인';

export function scopeRows(rows, selected='all') {
  const list=Array.isArray(rows)?rows:[];
  return list.filter(row=>row&&TREND_CATEGORIES.includes(String(row.category))&&
    (selected==='all'||String(row.category)===String(selected)));
}

export function observationKey(row={}) {
  return JSON.stringify([String(row.category||''),String(row.keyword||''),
    String(row.previousDate||''),String(row.currentDate||row.date||'')]);
}

const validDate=value=>typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)?value:null;
export function categorySources(value={}) {
  const summaries=Array.isArray(value.sourceSummaries)?value.sourceSummaries:[];
  return TREND_CATEGORIES.map(category=>{
    const summary=summaries.find(item=>String(item.category)===category);
    if(summary)return {category,categoryName:categoryName(category),
      sourceDate:validDate(summary.sourceDate),previousSourceDate:validDate(summary.previousSourceDate),
      lastChecked:summary.lastChecked||null,error:summary.error||null};
    // A legacy snapshot belongs only to its explicitly named single category.
    const isLegacy=String(value.settings?.category)===category;
    return {category,categoryName:categoryName(category),
      sourceDate:isLegacy?validDate(value.sourceDate||value.latestDate):null,
      previousSourceDate:isLegacy?validDate(value.previousSourceDate):null,
      lastChecked:isLegacy?(value.lastChecked||value.lastSuccessAt||null):null,
      error:isLegacy?(value.error||null):null};
  });
}

export function fixedSettings(minimumRise,newTop) {
  return {categories:[...TREND_CATEGORIES],category:TREND_CATEGORIES[0],
    minimumRise:Number(minimumRise),newTop:Number(newTop)};
}

export function notesForCategory(entries,category) {
  return (Array.isArray(entries)?entries:[]).filter(note=>
    String(note?.category||note?.comparison?.category||'')===String(category));
}
