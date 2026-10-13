import { Spin } from "antd";
import styles from "./PageLoading.module.less";

/** Suspense fallback for lazy route chunks: the global brand ring, centered. */
export default function PageLoading() {
  return (
    <div className={styles.host}>
      <Spin size="large" />
    </div>
  );
}
