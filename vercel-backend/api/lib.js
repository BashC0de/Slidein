// Simple in-memory device registry
// In production, use Vercel KV or a database
const devices = {};
const shareLinks = {};

function generateDeviceId() {
  return Math.random().toString(36).substring(2, 12);
}

function generateShareLinkId() {
  return Math.random().toString(36).substring(2, 15);
}

function registerDevice(deviceId, publicIp, localIp, friendName) {
  const now = Date.now();
  const expiryMs = 30 * 60 * 1000; // 30 minutes
  
  devices[deviceId] = {
    deviceId,
    publicIp,
    localIp,
    friendName,
    registeredAt: now,
    expiresAt: now + expiryMs,
    lastHeartbeat: now
  };
  
  return devices[deviceId];
}

function getDevice(deviceId) {
  const device = devices[deviceId];
  if (!device) return null;
  
  // Check if expired
  if (Date.now() > device.expiresAt) {
    delete devices[deviceId];
    return null;
  }
  
  return device;
}

function getDeviceByShareLink(shareLinkId) {
  const link = shareLinks[shareLinkId];
  if (!link) return null;
  
  const device = getDevice(link.deviceId);
  return device;
}

function createShareLink(deviceId, friendName) {
  const shareLinkId = generateShareLinkId();
  shareLinks[shareLinkId] = {
    shareLinkId,
    deviceId,
    friendName,
    createdAt: Date.now()
  };
  
  return shareLinkId;
}

module.exports = {
  generateDeviceId,
  generateShareLinkId,
  registerDevice,
  getDevice,
  getDeviceByShareLink,
  createShareLink,
  devices,
  shareLinks
};
