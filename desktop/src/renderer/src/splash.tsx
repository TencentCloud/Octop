import markUrl from "./assets/octop-mark.svg";
import { LinuxWindowControls } from "./linux-window-controls";
import { mount } from "./mount";
import "./base.less";
import styles from "./splash.module.less";

/**
 * Splash of the Early Window (§4). It owns no state: the main process loads the
 * Dashboard into this same window once ``/api/health`` is green, or replaces this
 * page with the failure Result.
 *
 * The sidecar can take ten seconds or more on a cold start, so the page has to
 * read as "working", not as "stuck on a blank screen": the mark, the product
 * name, one line saying what is being waited on, an indeterminate bar that keeps
 * moving, and the build number at the bottom for support. The wordmark already
 * says Octop, so the status line does not repeat it.
 *
 * 顶部 58px 的拖动热区由 base.less 提供，正文区域不参与窗口拖动。
 */
function Splash() {
  const version = new URLSearchParams(window.location.search).get("version");

  return (
    <main className={styles.splash} role="status" aria-live="polite">
      <LinuxWindowControls />
      <div className={styles.stack}>
        <div className={styles.mark} aria-hidden="true">
          <img className={styles.logo} src={markUrl} alt="" width={352} height={255} />
        </div>
        <h1 className={styles.wordmark}>Octop</h1>
        <p className={styles.text}>正在启动核心服务…</p>
        <div className={styles.bar} aria-hidden="true">
          <div className={styles.barThumb} />
        </div>
      </div>
      {version ? <p className={styles.version}>{version}</p> : null}
    </main>
  );
}

mount(<Splash />);
