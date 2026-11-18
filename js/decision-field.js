/* An original parametric trefoil sculpture. No 3D library or remote model is required. */
const vertex = `attribute vec3 aPosition;attribute vec3 aNormal;uniform mat3 uRotation;uniform float uScale;uniform float uAspect;uniform float uCamera;uniform vec2 uOffset;varying vec3 vNormal;varying vec3 vWorld;varying vec3 vLocal;void main(){vec3 p=uRotation*aPosition*uScale;p.xy+=uOffset;vWorld=p;vLocal=aPosition;vNormal=uRotation*aNormal;float z=uCamera-p.z;float t=.41421356;gl_Position=vec4(p.x/(uAspect*t),p.y/t,1.005*z-.2005,z);}`;
const fragment = `precision highp float;varying vec3 vNormal;varying vec3 vWorld;varying vec3 vLocal;uniform float uCamera;float hash(vec3 p){return fract(sin(dot(p,vec3(127.1,311.7,74.7)))*43758.5453);}void main(){vec3 n=normalize(vNormal);vec3 view=normalize(vec3(0.,0.,uCamera)-vWorld);vec3 l1=normalize(vec3(-3.,5.,6.)-vWorld);vec3 l2=normalize(vec3(5.,1.,2.)-vWorld);vec3 l3=normalize(vec3(-2.,-4.,3.)-vWorld);float d1=max(dot(n,l1),0.);float d2=max(dot(n,l2),0.);float d3=max(dot(n,l3),0.);float s1=pow(max(dot(n,normalize(l1+view)),0.),65.);float s2=pow(max(dot(n,normalize(l2+view)),0.),100.);float rim=pow(1.-max(dot(n,view),0.),2.5);float grain=hash(floor(vLocal*950.));float etch=sin(vLocal.y*760.+vLocal.x*42.)*.014;vec3 base=vec3(.115,.045,.21);vec3 col=base*(.35+d1*.65+d2*.3)+vec3(.42,.17,.77)*d1*.65+vec3(.12,.18,.38)*d2*.7+vec3(.18,.045,.3)*d3*.8+vec3(.82,.63,1.)*s1*1.25+vec3(.47,.69,1.)*s2*.8+vec3(.45,.21,.74)*rim*.4;col*=.86+.2*grain+etch;col=pow(col,vec3(.82));gl_FragColor=vec4(col,1.);}`;
const bgVertex = `attribute vec2 aPosition;varying vec2 vUV;void main(){vUV=aPosition*.5+.5;gl_Position=vec4(aPosition,0.,1.);}`;
const bgFragment = `precision highp float;varying vec2 vUV;uniform vec2 uSize;uniform float uTime;float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+1.),f.x),f.y);}void main(){vec2 uv=vUV;float aspect=uSize.x/uSize.y;vec2 p=(uv-vec2(.65,.56))*vec2(aspect,1.);float haze=exp(-dot(p,p)*2.9);float cloud=noise(uv*5.+vec2(uTime*.003,0.))*.6+noise(uv*13.)*.25+noise(uv*37.)*.15;vec3 col=vec3(.017,.018,.045)+vec3(.068,.026,.155)*haze*(.55+cloud);float horizon=exp(-pow((uv.y-.27)*7.,2.))*haze;col+=vec3(.023,.015,.053)*horizon;vec2 grid=uv*uSize/3.;float star=step(.99965,hash(floor(grid)))*pow(hash(floor(grid)+4.),3.);col+=vec3(.32,.29,.45)*star;float grain=(hash(gl_FragCoord.xy)-.5)*.018;col+=grain;col*=.76+.24*smoothstep(.1,.6,uv.y);gl_FragColor=vec4(col,1.);}`;

function normalize(v){const d=Math.hypot(...v)||1;return v.map(x=>x/d);}
function cross(a,b){return[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}
function curve(t){return[(1.28+.46*Math.cos(3*t))*Math.cos(2*t),(1.28+.46*Math.cos(3*t))*Math.sin(2*t),.65*Math.sin(3*t)];}
function geometry(rings,sides){
  const points=[];
  for(let i=0;i<=rings;i++){
    const t=i/rings*Math.PI*2,c=curve(t),next=curve(t+.001),tangent=normalize(next.map((n,k)=>n-c[k]));
    let normal=normalize(c);const dot=normal.reduce((s,n,k)=>s+n*tangent[k],0);
    normal=normalize(normal.map((n,k)=>n-dot*tangent[k]));const binormal=normalize(cross(tangent,normal));
    const ring=[];
    for(let j=0;j<=sides;j++){const v=j/sides*Math.PI*2,n=normal.map((a,k)=>a*Math.cos(v)+binormal[k]*Math.sin(v));ring.push([...c.map((a,k)=>a+n[k]*.265),...n]);}
    points.push(ring);
  }
  const out=[];
  for(let i=0;i<rings;i++)for(let j=0;j<sides;j++)for(const [a,b] of [[i,j],[i+1,j],[i,j+1],[i,j+1],[i+1,j],[i+1,j+1]])out.push(...points[a][b]);
  return new Float32Array(out);
}
function rotation(x,y,z){
  const a=Math.cos(x),b=Math.sin(x),c=Math.cos(y),d=Math.sin(y),e=Math.cos(z),f=Math.sin(z);
  return new Float32Array([c*e,a*f+b*d*e,b*f-a*d*e,-c*f,a*e-b*d*f,b*e+a*d*f,d,-b*c,a*c]);
}
export function createDecisionField(canvas,{reduced=false}={}){
  if(!canvas)return null;
  const gl=canvas.getContext('webgl',{alpha:false,antialias:true,powerPreference:'low-power',preserveDrawingBuffer:false});
  if(!gl)return null;
  let disposed=false,visible=true,motion=!reduced,progress=0,frame=0,lastDraw=0,width=1,height=1;
  const compile=(type,source)=>{const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)){console.warn('3D visual unavailable; using graphic fallback.');gl.deleteShader(s);throw Error('shader');}return s;};
  const program=(v,f)=>{const p=gl.createProgram(),vs=compile(gl.VERTEX_SHADER,v),fs=compile(gl.FRAGMENT_SHADER,f);gl.attachShader(p,vs);gl.attachShader(p,fs);gl.linkProgram(p);gl.deleteShader(vs);gl.deleteShader(fs);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error('program');return p;};
  let sculpture,background;
  try{sculpture=program(vertex,fragment);background=program(bgVertex,bgFragment);}catch{return null;}
  const uniform=(p,name)=>gl.getUniformLocation(p,name);
  const mesh=geometry(innerWidth<700?72:128,innerWidth<700?14:22),meshBuffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,meshBuffer);gl.bufferData(gl.ARRAY_BUFFER,mesh,gl.STATIC_DRAW);
  const bgBuffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bgBuffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]),gl.STATIC_DRAW);
  const sPosition=gl.getAttribLocation(sculpture,'aPosition'),sNormal=gl.getAttribLocation(sculpture,'aNormal'),bPosition=gl.getAttribLocation(background,'aPosition');
  const u={rotation:uniform(sculpture,'uRotation'),scale:uniform(sculpture,'uScale'),aspect:uniform(sculpture,'uAspect'),camera:uniform(sculpture,'uCamera'),offset:uniform(sculpture,'uOffset'),size:uniform(background,'uSize'),time:uniform(background,'uTime')};
  function resize(){const rect=canvas.getBoundingClientRect();width=rect.width;height=rect.height;const dpr=Math.min(devicePixelRatio||1,innerWidth<700?1.25:1.5);canvas.width=Math.max(1,Math.round(width*dpr));canvas.height=Math.max(1,Math.round(height*dpr));gl.viewport(0,0,canvas.width,canvas.height);draw(performance.now(),true);}
  function draw(time,once=false){
    if(disposed)return;
    if(!once){frame=0;if(!visible||document.hidden||!motion)return;if(time-lastDraw<32){frame=requestAnimationFrame(draw);return;}}
    lastDraw=time;const mobile=width<700,p=motion?progress:.55,t=motion?time*.000055:0;
    gl.clearColor(.02,.02,.05,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.disable(gl.DEPTH_TEST);gl.useProgram(background);gl.bindBuffer(gl.ARRAY_BUFFER,bgBuffer);gl.enableVertexAttribArray(bPosition);gl.vertexAttribPointer(bPosition,2,gl.FLOAT,false,0,0);gl.uniform2f(u.size,canvas.width,canvas.height);gl.uniform1f(u.time,motion?time*.001:0);gl.drawArrays(gl.TRIANGLES,0,3);gl.disableVertexAttribArray(bPosition);
    gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.useProgram(sculpture);gl.bindBuffer(gl.ARRAY_BUFFER,meshBuffer);gl.enableVertexAttribArray(sPosition);gl.vertexAttribPointer(sPosition,3,gl.FLOAT,false,24,0);gl.enableVertexAttribArray(sNormal);gl.vertexAttribPointer(sNormal,3,gl.FLOAT,false,24,12);
    gl.uniformMatrix3fv(u.rotation,false,rotation(.28+p*.7, -.35+p*.8+t, .15-p*.38));gl.uniform1f(u.scale,mobile?1.0-p*.2:1.38-p*.53);gl.uniform1f(u.aspect,width/height);gl.uniform1f(u.camera,mobile?6.6+p*1.7:5.7+p*2.4);gl.uniform2f(u.offset,mobile?.42+p*.12:1.0+p*.25,mobile?1.4-p*.55:.65-p*.25);gl.drawArrays(gl.TRIANGLES,0,mesh.length/6);gl.disableVertexAttribArray(sPosition);gl.disableVertexAttribArray(sNormal);canvas.classList.add('ready');
    if(!once&&motion&&visible&&!document.hidden)frame=requestAnimationFrame(draw);
  }
  function start(){if(!frame&&motion&&visible&&!document.hidden)frame=requestAnimationFrame(draw);}
  const io=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible){draw(performance.now(),true);start();}},{rootMargin:'100px'});io.observe(canvas);
  const visibility=()=>{if(document.hidden){cancelAnimationFrame(frame);frame=0;}else start();};
  const lost=e=>{e.preventDefault();canvas.classList.remove('ready');cancelAnimationFrame(frame);frame=0;};
  document.addEventListener('visibilitychange',visibility);canvas.addEventListener('webglcontextlost',lost);window.addEventListener('resize',resize,{passive:true});resize();start();
  return {setProgress(v){progress=Math.max(0,Math.min(1,v));if(!motion)draw(performance.now(),true);},setMotion(enabled){motion=enabled;if(!motion){cancelAnimationFrame(frame);frame=0;draw(performance.now(),true);}else start();},dispose(){disposed=true;cancelAnimationFrame(frame);io.disconnect();window.removeEventListener('resize',resize);document.removeEventListener('visibilitychange',visibility);canvas.removeEventListener('webglcontextlost',lost);gl.deleteBuffer(meshBuffer);gl.deleteBuffer(bgBuffer);gl.deleteProgram(sculpture);gl.deleteProgram(background);const ext=gl.getExtension('WEBGL_lose_context');ext?.loseContext();}};
}
