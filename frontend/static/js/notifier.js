export const Notifier = {
  logAdmin(message) {
    if (typeof console !== 'undefined') console.info(message);
  },
  showToast(message) {
    if (typeof console !== 'undefined') console.info(message);
  }
};

export default Notifier;
