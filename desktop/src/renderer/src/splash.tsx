import markUrl from "./assets/octop-mark.svg";
import { LinuxWindowControls } from "./linux-window-controls";
import { mount } from "./mount";
import "./base.css";
import "./splash.css";

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
 * 顶部 58px 的拖动热区由 base.css 提供，正文区域不参与窗口拖动。
 */
function Splash() {
  const version = new URLSearchParams(window.location.search).get("version");

  return (
    <main className="splash" role="status" aria-live="polite">
      <LinuxWindowControls />
      <div className="splash__stack">
        <div className="splash__mark" aria-hidden="true">
          <img className="splash__logo" src={markUrl} alt="" width={352} height={255} />
        </div>
        <h1 className="splash__wordmark">Octop</h1>
        <p className="splash__text">正在准备本地服务…</p>
        <div className="splash__bar" aria-hidden="true">
          <span className="splash__bar-thumb" />
        </div>
      </div>
      {version ? <p className="splash__version">v{version}</p> : null}
    </main>
  );
}

mount(<Splash />);
