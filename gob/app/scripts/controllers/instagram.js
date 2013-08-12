'use strict';

(function () {
  var InstagramCtrl = function ($http, $location, Feeds, ApiClient) {
    var access_token = jQuery.url(window.location).fparam('access_token');
    if (!access_token) {
      return;
    }

    $scope.access_token = access_token;

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

      Feeds.createFeed(data).then(function (feed) {
        $location.path('/feed/' + feed.feed_type + '/' + feed.feed_id);
      }, function () {
        window.alert('Something wen\'t wrong while saving your feed');
      }).always(updateLoader.stop);

    });
  };

  InstagramCtrl.$inject = ['$http', '$location', 'Feeds', 'ApiClient'];
  angular.module('pourOver').controller('InstagramCtrl', InstagramCtrl);
})();
