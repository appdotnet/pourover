'use strict';

(function () {
  var InstagramCtrl = function ($http, ApiClient) {
    var access_token = jQuery.url(window.location).fparam('access_token');
    console.log('Yo');
    if (!access_token) {
      return;
    }

    $http.jsonp('https://api.instagram.com/v1/users/self/', {
      params: {
        'access_token': access_token,
        'callback': 'JSON_CALLBACK'
      }
    }).success(function (resp) {
      var data = {
        feed_type: 2,
        access_token: access_token,
        username: resp.data.username,
        user_id: resp.data.id
      };

      ApiClient.post({
        url: 'feeds',
        data: data
      }).success(function (resp) {

      });
    });
  };

  InstagramCtrl.$inject = ['$http', 'ApiClient'];
  angular.module('pourOver').controller('InstagramCtrl', InstagramCtrl);
})();
