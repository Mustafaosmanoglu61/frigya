import { defineRailway, github, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const webVolume = volume("web-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 5000 });
  const web = service("web", {
    source: github("Mustafaosmanoglu61/frigya"),
    // Eski railway.json'dan: Dockerfile build (yalnızca webapp/ imaja girer)
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    healthcheck: "/healthz",
    healthcheckTimeout: 120,
    // `railway config migrate` restart policy'yi aktarmıyor — elle eklendi.
    // restartPolicyType ON_FAILURE Railway varsayılanı; yazılırsa IaC onu null
    // okuduğu için plan sürekli hayali fark gösteriyor, bu yüzden yazılmadı.
    deploy: { restartPolicyMaxRetries: 5 },
    replicas: { "sfo": 1 },
    // Custom domain IaC ile oluşturulamıyor: önce `railway domain <ad> --port 8080`,
    // sonra buraya ekle. DNS Hostinger'da (ottomantion.com): CNAME + _railway-verify TXT.
    domains: [{ domain: "frigya.ottomantion.com", port: 8080 }],
    volumeMounts: { "/data": webVolume },
    // Değerler Railway'de kalır; preserve() kaynak koda secret yazmaz
    env: { APP_ENV: preserve(), DB_PATH: preserve(), DB_RESTORE_TOKEN: preserve(), FRIGYA_API_TOKEN: preserve(), FRIGYA_API_TOKEN_USER: preserve(), INITIAL_ADMIN_EMAIL: preserve(), INITIAL_ADMIN_PASSWORD: preserve(), SESSION_SECRET: preserve() },
  });

  return project("frigya", {
    resources: [web, webVolume],
  });
});
