快速开始
#开发环境
从 vite v7.0.0 (opens new window)版本后，规定 node 版本号应不小于 20.19.0 （优先推荐安装长期维护LTS版，如下图）

nodejs 官网 (opens new window)当然也可以安装 .nvmrc (opens new window)推荐的 node 版本


从 vue-pure-admin v5.0.0 版本后，规定 pnpm 版本号应不小于 9

如果您还没安装 pnpm，请执行下面命令进行安装（mac 用户遇到安装报错请在命令前加上 sudo）

npm install -g pnpm

如果您需要安装多个 node 版本环境，请参考 Node.js 版本管理工具

如果您觉得安装平台依赖慢，请参考 npmmirror

#IDE
如果您使用的 IDE 是 vscode (opens new window)（推荐），请点击这里并安装推荐的插件，可提高开发效率

#拉取代码
#推荐使用 @pureadmin/cli 脚手架

img

全局安装
npm install -g @pureadmin/cli
交互式选择模板并创建项目
pure create
点我查看 @pureadmin/cli 脚手架详细用法(opens new window)

#从 GitHub 上拉取
#完整版前端代码
git clone https://github.com/pure-admin/vue-pure-admin.git
#国际化精简版前端代码
git clone -b i18n https://github.com/pure-admin/pure-admin-thin.git
#非国际化精简版前端代码
git clone https://github.com/pure-admin/pure-admin-thin.git
#tauri 版本前端代码
git clone https://github.com/pure-admin/tauri-pure-admin.git
#electron 版本前端代码
git clone https://github.com/pure-admin/electron-pure-admin.git
#后端代码（node 版本）
git clone https://github.com/pure-admin/pure-admin-backend.git
#本地开发
#安装依赖
pnpm install
#启动平台
pnpm dev
#项目打包
pnpm build
#安装一个包
pnpm add 包名
#卸载一个包
pnpm remove 包名