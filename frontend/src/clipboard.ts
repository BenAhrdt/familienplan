function legacyCopy(text:string):Promise<void>{
  const field=document.createElement('textarea')
  field.value=text
  field.setAttribute('readonly','')
  field.style.position='fixed'
  field.style.opacity='0'
  document.body.appendChild(field)
  field.select()
  const copied=document.execCommand('copy')
  field.remove()
  return copied?Promise.resolve():Promise.reject(new Error('Kopieren wurde vom Browser blockiert'))
}

const nativeWrite=navigator.clipboard?.writeText?.bind(navigator.clipboard)
const writeText=(text:string)=>nativeWrite?nativeWrite(text).catch(()=>legacyCopy(text)):legacyCopy(text)

try{
  Object.defineProperty(navigator,'clipboard',{configurable:true,value:{...navigator.clipboard,writeText}})
}catch{
  // Very restrictive browsers may not allow replacing navigator.clipboard.
}
