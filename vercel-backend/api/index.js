export default function handler(req, res) {
  res.status(200).json({
    name: 'Trackpad Cloud Relay',
    version: '1.0.0',
    endpoints: {
      generateLink: 'POST /api/generate-link { friendName }',
      register: 'POST /api/register { deviceId, publicIp, localIp, friendName }',
      device: 'GET /api/device?id=<deviceId>',
      shareLink: 'GET /api/share/<shareLinkId>'
    }
  });
}
