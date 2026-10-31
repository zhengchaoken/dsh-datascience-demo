/**
 * dsh-datascience-demo — 宿主端入口。
 *
 * 本插件的界面完全在浏览器端（src/client/index.ts）。宿主端只需要作为
 * 一个合法的 cordis 插件行存在，让 loader 能把 `dsh.client` 声明的 client
 * 半加载进 web GUI。
 */

/** 稳定的 cordis 插件名（与 cordis.patch.yml 中的 id 对应）。 */
export const name = 'datascience-demo'

/** 目前没有宿主侧能力：面板就是一个空白界面。 */
export function apply(): void {}
