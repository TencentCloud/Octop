import { createStyles } from "antd-style";
import { Sun, Cloud, CloudRain } from "lucide-react";
import { Card, Typography } from "antd";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useServerTimezone } from "../../../hooks/useServerTimezone";

interface WeatherItem {
  location: string;
  weather: string;
  temperature: number;
  date: string;
}

const useStyles = createStyles(({ css }) => ({
  container: css`
    width: 100%;
    max-width: 320px;
    border-radius: var(--fn-radius-xl);
    background: linear-gradient(135deg, #6366f1 0%, #4338ca 100%);
    color: white;
    overflow: hidden;
    box-shadow: var(--fn-shadow-lg);
    border: none;

    .ant-card-body {
      padding: 0;
    }
  `,
  header: css`
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  `,
  location: css`
    font-size: 24px;
    font-weight: 600;
    margin-bottom: 4px;
    color: white !important;
  `,
  date: css`
    font-size: 14px;
    opacity: 0.8;
    color: white !important;
  `,
  mainWeather: css`
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 24px 0 32px;
  `,
  tempContainer: css`
    display: flex;
    align-items: flex-start;
    line-height: 1;
  `,
  temperature: css`
    font-size: 64px;
    font-weight: 700;
    color: white !important;
  `,
  degree: css`
    font-size: 24px;
    font-weight: 500;
    margin-top: 8px;
    color: white !important;
  `,
  mainIcon: css`
    font-size: 48px;
    margin-bottom: 16px;
    filter: drop-shadow(0 4px 4px rgba(0, 0, 0, 0.2));
  `,
  condition: css`
    font-size: 16px;
    font-weight: 500;
    margin-top: 8px;
    opacity: 0.9;
    color: white !important;
  `,
  forecast: css`
    background: rgba(255, 255, 255, 0.1);
    backdrop-filter: blur(10px);
    padding: 16px 24px;
  `,
  forecastItem: css`
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);

    &:last-child {
      border-bottom: none;
      padding-bottom: 4px;
    }

    &:first-of-type {
      padding-top: 4px;
    }
  `,
  forecastDay: css`
    font-size: 14px;
    width: 60px;
    color: white !important;
  `,
  forecastIcon: css`
    font-size: 20px;
    color: white;
  `,
  forecastTemp: css`
    font-size: 14px;
    font-weight: 500;
    width: 40px;
    text-align: right;
    color: white !important;
  `,
}));

const WeatherIcon = ({
  type,
  className,
}: {
  type: string;
  className?: string;
}) => {
  switch (type) {
    case "sunny":
      return <Sun className={className} />;
    case "rainy":
      return <CloudRain className={className} />;
    case "cloudy":
      return <Cloud className={className} />;
    default:
      return <Sun className={className} />;
  }
};

const getWeatherLabel = (type: string) => {
  switch (type) {
    case "sunny":
      return "晴朗";
    case "rainy":
      return "雨天";
    case "cloudy":
      return "多云";
    default:
      return type;
  }
};

function weatherDate(date: string, timeZone: string, lang: string): string {
  const raw = date.includes("T") ? date : `${date}T12:00:00Z`;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString(lang.startsWith("zh") ? "zh-CN" : "en-US", {
    timeZone,
    month: "2-digit",
    day: "2-digit",
    weekday: "long",
  });
}

function weatherWeekday(date: string, timeZone: string, lang: string): string {
  const raw = date.includes("T") ? date : `${date}T12:00:00Z`;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString(lang.startsWith("zh") ? "zh-CN" : "en-US", {
    timeZone,
    weekday: "short",
  });
}

export default function Weather(props: {
  data: { content: Array<{ data: { output: string } }> };
}) {
  const { styles } = useStyles();
  const { i18n } = useTranslation();
  const timeZone = useServerTimezone();
  const data = useMemo(() => {
    try {
      const content = props.data?.content;
      if (!content || content.length < 2) {
        return [];
      }
      const output = content[1]?.data?.output;
      if (!output) {
        return [];
      }
      return JSON.parse(JSON.parse(output));
    } catch {
      return [];
    }
  }, [props.data.content]);

  if (!data?.length) return null;
  const current = data[0] as WeatherItem;
  const forecast = data.slice(1) as WeatherItem[];
  return (
    <Card className={styles.container} bordered={false}>
      <div className={styles.header}>
        <div>
          <Typography.Text className={styles.location}>
            {current.location}
          </Typography.Text>
          <br />
          <Typography.Text className={styles.date}>
            {weatherDate(current.date, timeZone, i18n.language)}
          </Typography.Text>
        </div>
      </div>

      <div className={styles.mainWeather}>
        <WeatherIcon type={current.weather} className={styles.mainIcon} />
        <div className={styles.tempContainer}>
          <Typography.Text className={styles.temperature}>
            {current.temperature}
          </Typography.Text>
          <Typography.Text className={styles.degree}>°C</Typography.Text>
        </div>
        <Typography.Text className={styles.condition}>
          {getWeatherLabel(current.weather)}
        </Typography.Text>
      </div>

      <div className={styles.forecast}>
        {forecast.map((item: WeatherItem, index: number) => (
          <div key={index} className={styles.forecastItem}>
            <Typography.Text className={styles.forecastDay}>
              {weatherWeekday(item.date, timeZone, i18n.language)}
            </Typography.Text>
            <WeatherIcon type={item.weather} className={styles.forecastIcon} />
            <Typography.Text className={styles.forecastTemp}>
              {item.temperature}°
            </Typography.Text>
          </div>
        ))}
      </div>
    </Card>
  );
}
