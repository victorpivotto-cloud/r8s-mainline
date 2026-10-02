/* Tiny headless EGL test: select the real DRM render node, clear/read 4x4.
 * Uses dlopen so it does not require EGL development packages on the phone.
 * ABI constants follow Khronos EGL/GLES registries. No display mode changes.
 */
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
typedef void *Handle;
typedef unsigned int Bool;
typedef int Int;
#define LOAD(lib, name, ret, args) ret (*name) args = dlsym(lib, #name); if (!name) {fprintf(stderr,"missing %s\n",#name); return 2;}
#define REQUIRE(expr) do {if (!(expr)) {fprintf(stderr,"FAIL: %s; EGL=0x%x\n",#expr,eglGetError()); return 1;}} while (0)
int main(void) {
 void *egl=dlopen("libEGL.so.1",RTLD_NOW|RTLD_LOCAL);
 void *gles=dlopen("libGLESv2.so.2",RTLD_NOW|RTLD_LOCAL);
 if (!egl || !gles) {fputs("EGL/GLES libraries unavailable\n",stderr);return 2;}
 LOAD(egl,eglGetProcAddress,void *, (const char *));
 LOAD(egl,eglGetError,Int,(void));
 LOAD(egl,eglInitialize,Bool,(Handle,Int *,Int *));
 LOAD(egl,eglBindAPI,Bool,(unsigned int));
 LOAD(egl,eglChooseConfig,Bool,(Handle,const Int *,Handle *,Int,Int *));
 LOAD(egl,eglCreatePbufferSurface,Handle,(Handle,Handle,const Int *));
 LOAD(egl,eglCreateContext,Handle,(Handle,Handle,Handle,const Int *));
 LOAD(egl,eglMakeCurrent,Bool,(Handle,Handle,Handle,Handle));
 LOAD(egl,eglDestroyContext,Bool,(Handle,Handle));
 LOAD(egl,eglDestroySurface,Bool,(Handle,Handle));
 LOAD(egl,eglTerminate,Bool,(Handle));
 Bool (*query)(Int,Handle *,Int *)=eglGetProcAddress("eglQueryDevicesEXT");
 const char *(*device_string)(Handle,Int)=eglGetProcAddress("eglQueryDeviceStringEXT");
 Handle (*platform)(unsigned int,Handle,const Int *)=eglGetProcAddress("eglGetPlatformDisplayEXT");
 if (!query || !device_string || !platform) {fputs("device EGL extensions unavailable\n",stderr);return 2;}
 Handle devices[16],device=NULL; Int count=0;
 REQUIRE(query(16,devices,&count));
 for(Int i=0;i<count;i++) {
  const char *node=device_string(devices[i],0x3377);
  printf("EGL device %d render_node=%s\n",i,node ? node : "none");
  if(node && strcmp(node,"/dev/dri/renderD128")==0) device=devices[i];
 }
 if(!device) {fputs("real render node unavailable via EGL\n",stderr);return 2;}
 Handle display=platform(0x313f,device,NULL);Int major=0,minor=0;
 REQUIRE(display); REQUIRE(eglInitialize(display,&major,&minor));
 printf("EGL %d.%d initialized on renderD128\n",major,minor);
 REQUIRE(eglBindAPI(0x30a0));
 const Int attrs[]={0x3033,1,0x3040,4,0x3024,8,0x3023,8,0x3022,8,0x3021,8,0x3038};
 Handle config=NULL;Int configs=0;
 REQUIRE(eglChooseConfig(display,attrs,&config,1,&configs));REQUIRE(configs==1);
 const Int size[]={0x3057,4,0x3056,4,0x3038};
 Handle surface=eglCreatePbufferSurface(display,config,size);REQUIRE(surface);
 const Int context_attrs[]={0x3098,2,0x3038};
 Handle context=eglCreateContext(display,config,NULL,context_attrs);REQUIRE(context);
 REQUIRE(eglMakeCurrent(display,surface,surface,context));
 LOAD(gles,glGetString,const unsigned char *, (unsigned int));
 LOAD(gles,glClearColor,void,(float,float,float,float));
 LOAD(gles,glClear,void,(unsigned int));
 LOAD(gles,glReadPixels,void,(Int,Int,Int,Int,unsigned int,unsigned int,void *));
 LOAD(gles,glGetError,unsigned int,(void));
 const char *renderer=(const char *)glGetString(0x1f01);
 const char *version=(const char *)glGetString(0x1f02);
 printf("renderer=%s\nversion=%s\n",renderer ? renderer : "none",version ? version : "none");
 REQUIRE(renderer && strstr(renderer,"Mali-G77"));
 unsigned char pixels[4*4*4]={0};
 glClearColor(1.0f,0.0f,0.0f,1.0f);glClear(0x4000);
 glReadPixels(0,0,4,4,0x1908,0x1401,pixels);
 REQUIRE(glGetError()==0);
 for(Int i=0;i<16;i++) REQUIRE(pixels[i*4]==255 && pixels[i*4+1]==0 && pixels[i*4+2]==0 && pixels[i*4+3]==255);
 LOAD(gles,glCreateShader,unsigned int,(unsigned int));
 LOAD(gles,glShaderSource,void,(unsigned int,Int,const char *const *,const Int *));
 LOAD(gles,glCompileShader,void,(unsigned int));
 LOAD(gles,glGetShaderiv,void,(unsigned int,unsigned int,Int *));
 LOAD(gles,glCreateProgram,unsigned int,(void));
 LOAD(gles,glAttachShader,void,(unsigned int,unsigned int));
 LOAD(gles,glBindAttribLocation,void,(unsigned int,unsigned int,const char *));
 LOAD(gles,glLinkProgram,void,(unsigned int));
 LOAD(gles,glGetProgramiv,void,(unsigned int,unsigned int,Int *));
 LOAD(gles,glUseProgram,void,(unsigned int));
 LOAD(gles,glGenBuffers,void,(Int,unsigned int *));
 LOAD(gles,glBindBuffer,void,(unsigned int,unsigned int));
 LOAD(gles,glBufferData,void,(unsigned int,long,const void *,unsigned int));
 LOAD(gles,glEnableVertexAttribArray,void,(unsigned int));
 LOAD(gles,glVertexAttribPointer,void,(unsigned int,Int,unsigned int,unsigned char,Int,const void *));
 LOAD(gles,glViewport,void,(Int,Int,Int,Int));
 LOAD(gles,glDrawArrays,void,(unsigned int,Int,Int));
 LOAD(gles,glDeleteBuffers,void,(Int,const unsigned int *));
 LOAD(gles,glDeleteProgram,void,(unsigned int));
 LOAD(gles,glDeleteShader,void,(unsigned int));
 const char *shader_text[]={"attribute vec2 position; void main(){gl_Position=vec4(position,0.0,1.0);}","precision mediump float; void main(){gl_FragColor=vec4(0.0,1.0,0.0,1.0);}"};
 unsigned int shaders[]={glCreateShader(0x8b31),glCreateShader(0x8b30)};
 for(Int i=0;i<2;i++) {Int ok=0;glShaderSource(shaders[i],1,&shader_text[i],NULL);glCompileShader(shaders[i]);glGetShaderiv(shaders[i],0x8b81,&ok);REQUIRE(ok);}
 unsigned int program=glCreateProgram();Int linked=0;
 glAttachShader(program,shaders[0]);glAttachShader(program,shaders[1]);
 glBindAttribLocation(program,0,"position");glLinkProgram(program);
 glGetProgramiv(program,0x8b82,&linked);REQUIRE(linked);glUseProgram(program);
 const float vertices[]={-1.0f,-1.0f,3.0f,-1.0f,-1.0f,3.0f};unsigned int buffer=0;
 glGenBuffers(1,&buffer);glBindBuffer(0x8892,buffer);glBufferData(0x8892,sizeof(vertices),vertices,0x88e4);
 glEnableVertexAttribArray(0);glVertexAttribPointer(0,2,0x1406,0,0,NULL);
 glViewport(0,0,4,4);glDrawArrays(0x0004,0,3);
 memset(pixels,0,sizeof(pixels));glReadPixels(0,0,4,4,0x1908,0x1401,pixels);REQUIRE(glGetError()==0);
 for(Int i=0;i<16;i++) REQUIRE(pixels[i*4]==0 && pixels[i*4+1]==255 && pixels[i*4+2]==0 && pixels[i*4+3]==255);
 glDeleteBuffers(1,&buffer);glDeleteProgram(program);glDeleteShader(shaders[0]);glDeleteShader(shaders[1]);
 REQUIRE(eglMakeCurrent(display,NULL,NULL,NULL));
 REQUIRE(eglDestroyContext(display,context));REQUIRE(eglDestroySurface(display,surface));REQUIRE(eglTerminate(display));
 puts("PASS: Mali-G77 EGL clear and GLSL triangle/readback; 16 green pixels; no display mode change");
 dlclose(gles);dlclose(egl);return 0;
}
